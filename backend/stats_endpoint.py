# Add this route to backend/main.py
# Paste it after any existing GET route, e.g. after /api/search

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Live archive stats — article count, oldest, newest."""
    try:
        keys = r.keys('article:*')
        count = len(keys)

        # Get oldest and newest from sorted timestamps
        oldest = None
        newest = None
        if count > 0:
            timestamps = []
            pipe = r.pipeline()
            for key in keys:
                pipe.hget(key, 'timestamp')
            results = pipe.execute()
            timestamps = [t for t in results if t]
            if timestamps:
                timestamps.sort()
                oldest = timestamps[0]
                newest = timestamps[-1]

        return jsonify({
            'article_count': count,
            'oldest': oldest,
            'newest': newest,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
