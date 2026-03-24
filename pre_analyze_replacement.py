# =============================================================================
# DROP-IN REPLACEMENT for pre_analyze() in main.py
# Replace the entire @app.route('/api/pre_analyze', ...) block with this.
#
# Changes from v2.0:
#   - VADER pos/neg/neu breakdown stored (not just compound)
#   - Entity counts by type (PERSON, ORG, GPE, LOC, DATE, MONEY, EVENT)
#   - Full lemma list extracted and stored
#   - Noun chunk count
#   - Sentence count + avg sentence length
#   - Additional textstat metrics: Coleman-Liau, SMOG, Dale-Chall, syllable count
#   - Word count stored
#   - All new fields written to article:{id} hash in Redis when called from scribe
#     (scribe passes article_id in request body — optional, ignored if absent)
#   - All new fields returned in JSON response (scribe stores dossier in Redis)
#   - Grafana-ready: corpus_exporter.py reads these fields from article hashes
# =============================================================================

@app.route('/api/pre_analyze', methods=['POST'])
def pre_analyze():
    """
    Pre-analysis endpoint - Fast quality assessment with FAIR scoring.

    CHIMERA SCORE v2.0 (FAIR):
    - Based purely on objectivity (0-100 scale)
    - No penalty for technical writing complexity
    - Readability grade still measured for transparency
    - Reading level classification provided as metadata

    v3.0 additions (instrumentation pass):
    - Full VADER breakdown (pos/neg/neu/compound)
    - Entity counts by NER type
    - Lemma extraction (top 50 by frequency, stopwords excluded)
    - Noun chunk count
    - Sentence count + avg sentence length
    - Coleman-Liau, SMOG, Dale-Chall readability scores
    - Word count, syllable count
    - All metrics written into article:{id} hash if article_id provided
    """
    if not all([NLP_PROCESSOR, SENTIMENT_ANALYZER]):
        app.logger.error("🔥 NLP Engine unavailable for pre_analyze")
        return jsonify({"error": "NLP Engine is offline."}), 503

    data = request.get_json()
    input_text  = data.get('inputText', '')
    article_id  = data.get('article_id', '')   # optional — scribe passes this

    if not input_text:
        return jsonify({"chimera_score": 0.0, "sentiment": 0.0, "entities_found": []})

    input_text_snippet = input_text[:MAX_CONTENT_CHARS]

    try:
        analyze_start = time.perf_counter()

        # --- VADER sentiment (full breakdown) ---
        vader_scores  = SENTIMENT_ANALYZER.polarity_scores(input_text_snippet)
        sentiment     = vader_scores.get('compound', 0.0)
        vader_pos     = round(vader_scores.get('pos', 0.0), 4)
        vader_neg     = round(vader_scores.get('neg', 0.0), 4)
        vader_neu     = round(vader_scores.get('neu', 0.0), 4)

        # --- TextBlob objectivity ---
        blob           = TextBlob(input_text_snippet)
        subjectivity   = blob.sentiment.subjectivity
        objectivity_score = (1 - subjectivity) * 100
        chimera_score  = round(objectivity_score / 100, 4)

        # --- Readability suite ---
        readability_grade   = textstat.flesch_kincaid_grade(input_text_snippet)
        reading_level       = classify_reading_level(readability_grade)
        coleman_liau        = round(textstat.coleman_liau_index(input_text_snippet), 2)
        smog_index          = round(textstat.smog_index(input_text_snippet), 2)
        dale_chall          = round(textstat.dale_chall_readability_score(input_text_snippet), 2)
        syllable_count      = textstat.syllable_count(input_text_snippet)
        word_count          = textstat.lexicon_count(input_text_snippet, removepunct=True)
        sentence_count      = textstat.sentence_count(input_text_snippet)
        avg_sentence_len    = round(word_count / max(sentence_count, 1), 1)

        # --- spaCy NLP ---
        doc = NLP_PROCESSOR(input_text_snippet)

        # Entity counts by type
        entity_labels = ["PERSON", "ORG", "GPE", "LOC", "DATE", "MONEY", "EVENT"]
        entity_counts = {label: 0 for label in entity_labels}
        entities_found = []
        for ent in doc.ents:
            if ent.label_ in entity_counts:
                entity_counts[ent.label_] += 1
                entities_found.append(ent.label_)

        # Lemmas — top 50 content words, stopwords and punct excluded
        STOP_LABELS = {"SPACE", "PUNCT", "SYM", "NUM", "X"}
        lemma_freq = {}
        for token in doc:
            if (not token.is_stop and not token.is_punct and not token.is_space
                    and token.pos_ not in STOP_LABELS and len(token.lemma_) > 2):
                lemma = token.lemma_.lower()
                lemma_freq[lemma] = lemma_freq.get(lemma, 0) + 1
        top_lemmas = sorted(lemma_freq, key=lemma_freq.get, reverse=True)[:50]

        # Noun chunks
        noun_chunk_count = len(list(doc.noun_chunks))

        analyze_duration = (time.perf_counter() - analyze_start) * 1000

        app.logger.info(
            f"✅ Pre-analysis v3.0 in {analyze_duration:.0f}ms "
            f"(chimera={chimera_score}, obj={objectivity_score:.0f}, "
            f"grade={readability_grade:.1f}, words={word_count}, "
            f"entities={sum(entity_counts.values())})"
        )

        result = {
            # --- Core scores (unchanged) ---
            "chimera_score":        chimera_score,
            "sentiment":            sentiment,
            "subjectivity":         round(subjectivity, 4),
            "objectivity_score":    round(objectivity_score, 2),
            "readability_grade":    round(readability_grade, 1),
            "reading_level":        reading_level,
            "entities_found":       list(set(entities_found)),

            # --- New: VADER breakdown ---
            "vader_pos":            vader_pos,
            "vader_neg":            vader_neg,
            "vader_neu":            vader_neu,

            # --- New: entity counts by type ---
            "entity_person_count":  entity_counts["PERSON"],
            "entity_org_count":     entity_counts["ORG"],
            "entity_gpe_count":     entity_counts["GPE"],
            "entity_loc_count":     entity_counts["LOC"],
            "entity_date_count":    entity_counts["DATE"],
            "entity_money_count":   entity_counts["MONEY"],
            "entity_event_count":   entity_counts["EVENT"],

            # --- New: text structure ---
            "word_count":           word_count,
            "sentence_count":       sentence_count,
            "avg_sentence_len":     avg_sentence_len,
            "syllable_count":       syllable_count,
            "noun_chunk_count":     noun_chunk_count,

            # --- New: readability suite ---
            "coleman_liau":         coleman_liau,
            "smog_index":           smog_index,
            "dale_chall":           dale_chall,

            # --- New: lemmas (stored as space-separated string for Redis) ---
            "top_lemmas":           " ".join(top_lemmas),
        }

        # --- Write extended fields to Redis article hash if article_id provided ---
        # Scribe passes article_id so these metrics land in the hash immediately.
        # corpus_exporter.py reads them from there.
        if article_id and r:
            try:
                redis_fields = {
                    "nlp_chimera_score":     str(chimera_score),
                    "nlp_sentiment":         str(sentiment),
                    "nlp_vader_pos":         str(vader_pos),
                    "nlp_vader_neg":         str(vader_neg),
                    "nlp_vader_neu":         str(vader_neu),
                    "nlp_subjectivity":      str(round(subjectivity, 4)),
                    "nlp_objectivity":       str(round(objectivity_score, 2)),
                    "nlp_word_count":        str(word_count),
                    "nlp_sentence_count":    str(sentence_count),
                    "nlp_avg_sentence_len":  str(avg_sentence_len),
                    "nlp_syllable_count":    str(syllable_count),
                    "nlp_noun_chunk_count":  str(noun_chunk_count),
                    "nlp_fk_grade":          str(round(readability_grade, 1)),
                    "nlp_reading_level":     reading_level,
                    "nlp_coleman_liau":      str(coleman_liau),
                    "nlp_smog":              str(smog_index),
                    "nlp_dale_chall":        str(dale_chall),
                    "nlp_entity_person":     str(entity_counts["PERSON"]),
                    "nlp_entity_org":        str(entity_counts["ORG"]),
                    "nlp_entity_gpe":        str(entity_counts["GPE"]),
                    "nlp_entity_loc":        str(entity_counts["LOC"]),
                    "nlp_entity_date":       str(entity_counts["DATE"]),
                    "nlp_entity_money":      str(entity_counts["MONEY"]),
                    "nlp_entity_event":      str(entity_counts["EVENT"]),
                    "nlp_top_lemmas":        " ".join(top_lemmas),
                }
                r.hset(f"article:{article_id}", mapping=redis_fields)
                app.logger.debug(f"📊 NLP fields written to article:{article_id}")
            except Exception as redis_err:
                app.logger.warning(f"⚠️  NLP Redis write failed (non-fatal): {redis_err}")

        return jsonify(result)

    except Exception as e:
        app.logger.error(f"🔥 Pre-analysis failed: {e}", exc_info=True)
        return jsonify({"chimera_score": 0.0, "sentiment": 0.0, "entities_found": []})
