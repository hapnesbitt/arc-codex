// Arc Codex — four-node architecture diagram.
//
// INTERNAL. Not public. The public developer page at /about/developer
// describes roles, never machines; this diagram is for Ross and may name
// or number the nodes plainly.
//
// Plain box-drawing typst: no #import, no @preview package, no registry
// dependency. Compiles offline with just `typst compile`.
//
// Rebuild: typst compile ops/four_node_architecture.typ

#set page(paper: "us-letter", flipped: true, margin: 0.55in)
#set text(font: ("Liberation Sans", "DejaVu Sans"), size: 10pt)

#align(center)[
  #text(20pt, weight: "bold")[Arc Codex — Four-Node Architecture]
  #v(2pt)
  #text(9pt, fill: gray)[
    Role separation settled 2026-09-11 · internal reference, not the public page
  ]
]

#v(0.35in)

// The diagram itself. A monospace block preserves the whitespace exactly,
// which is the point: alignment IS the drawing.
#align(center)[
  #set text(font: ("DejaVu Sans Mono", "Liberation Mono"), size: 9.5pt)
  #block(spacing: 0pt)[
    #raw(block: true,
"    ┌──────────────────────────────┐   articles    ┌──────────────────────────────┐
    │                              │  ──────────▶  │                              │
    │   INGEST · STORE · SERVE     │               │           ANALYSIS           │
    │   (node 1)                   │               │           (node 2)           │
    │                              │               │                              │
    │   • RSS ingestion (Scribe)   │               │   • local analysis model     │
    │   • datastore                │               │   • three ARC passes         │
    │   • search index             │               │       (Red / Blue / Purple)  │
    │   • feed & article pages     │               │   • broadcast-script pass    │
    │   • publication & posting    │               │       writes an original     │
    │                              │               │       short piece drawn      │
    │                              │               │       from those findings    │
    │                              │               │                              │
    └──────────────────────────────┘               └──────────────────────────────┘
                  ▲                                                │
                  │                                                │
                  │  MP3                     broadcast script      │
                  │                                                │
                  │                                                ▼
                  │                                ┌──────────────────────────────┐
                  │                                │                              │
                  │                                │          SYNTHESIS           │
                  │                                │           (node 3)           │
                  └────────────────────────────────│                              │
                                                   │   • Kokoro neural TTS        │
                                                   │   • reads the broadcast      │
                                                   │       script, not the source │
                                                   │       article                │
                                                   │   • emits mono MP3           │
                                                   │                              │
                                                   │   dedicated role; no other   │
                                                   │   node produces speech       │
                                                   │                              │
                                                   └──────────────────────────────┘


    ┌──────────────────────────────┐
    │                              │
    │      PORTABLE AUTHORING      │
    │           (node 4)           │
    │                              │
    │   offline authoring work;    │
    │   not in the live pipeline;  │
    │   syncs when online          │
    │                              │
    └──────────────────────────────┘
")
  ]
]

#v(0.3in)

#pad(x: 0.5in)[
  #text(size: 10pt)[
    *Flow — five stages, four nodes, three inter-node hops.*
  ]
  #v(4pt)
  #text(size: 9.5pt)[
    1. *Ingest* — node 1 pulls RSS and lands new articles in the datastore. \
    2. *Analysis* — node 2 picks up jobs from the datastore, runs the three ARC
       passes lazily on an article's first view. \
    3. *Broadcast script* — still on node 2: an additional analysis pass writes
       an original short piece from the Red/Blue/Purple findings. This piece,
       not the source article, is what gets read aloud. \
    4. *Synthesis* — node 3 picks up the broadcast script from the datastore
       and renders it to mono MP3 with Kokoro. \
    5. *Publication* — node 1 serves the article, its analysis, and the audio
       to readers.
  ]
]

#v(0.15in)

#pad(x: 0.5in)[
  #text(size: 8.5pt, fill: gray)[
    Node 4 (portable authoring) is off-pipeline by design: it exists so authoring
    work can proceed without the fleet reachable, and it syncs back when it
    rejoins. It never handles live ingest, analysis, synthesis, or publication.
  ]
  #v(4pt)
  #text(size: 8.5pt, fill: gray)[
    All hops between nodes are mediated by the datastore on node 1; there is no
    direct node-to-node channel. That is intentional — node 1's availability is
    already required for the site to serve, so making it the queue substrate
    adds no new failure surface.
  ]
]
