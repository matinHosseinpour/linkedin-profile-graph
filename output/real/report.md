# Profile graph analysis

Dataset: **observed**. Input profiles: **10**. Selected profiles: **10**.

Open [interactive.html](interactive.html) for the offline explorer: select people, posts or edges to inspect captured activity, source links and shared-skill evidence. Search, filter, drag nodes, zoom and export the current view as JSON.

Only the supplied snapshots are analyzed; this is not a complete organization census.

Organization filter: none. Skill-affinity edges: **2**. Observed activity edges inside this cohort: **14**.

## Findings in this sample

- Highest observed incoming reach: **Thomas Wolf**, with **4** distinct counterparties. This is a count within the captured cohort.
- Highest observed outgoing reach: **Chun Te Lee, Clem Delangue 🤗**, with **3** distinct counterparties. This is a count within the captured cohort.
- Highest directed betweenness: **Thomas Wolf** (0.0208). This measures shortest-path brokerage in this observed graph only.
- The skill graph has **2** edges and **8** components. Sparse visible skill overlap limits what can be concluded; missing edges do not establish a lack of real ties.

## Method

Skill names use Unicode NFKC normalization, case folding and whitespace normalization. No synonyms, job roles, dates or missing skills are invented. Pairs are linked when Jaccard(shared skills / union of skills) >= 0.25. Edge weight is that similarity. Missing skill lists produce no affinity edges.

Degree centrality uses the selected cohort denominator (n - 1); a singleton scores zero. Normalized betweenness uses unweighted shortest paths. Strength sums similarity weights. Communities use greedy weighted modularity. Skill layout: circular; spring layout seed is 42. These are graph algorithms; no predictive ML model is trained.

## Centrality within the observed skill graph

| Person | Degree | Betweenness | Strength | Community |
| --- | ---: | ---: | ---: | ---: |
| Ben Burtenshaw | 0.1111 | 0.0000 | 0.3333 | 1 |
| Pénélope GITTOS | 0.1111 | 0.0000 | 0.3333 | 1 |
| Lysandre Debut | 0.1111 | 0.0000 | 0.3333 | 2 |
| Thomas Wolf | 0.1111 | 0.0000 | 0.3333 | 2 |
| Chun Te Lee | 0.0000 | 0.0000 | 0.0000 | 3 |
| Clem Delangue 🤗 | 0.0000 | 0.0000 | 0.0000 | 4 |
| Dana Aubakirova | 0.0000 | 0.0000 | 0.0000 | 5 |
| Julien Chaumond | 0.0000 | 0.0000 | 0.0000 | 6 |
| Matthew Douglas | 0.0000 | 0.0000 | 0.0000 | 7 |
| Remi Fabre | 0.0000 | 0.0000 | 0.0000 | 8 |

## Centrality within the observed directed activity graph

Arrow direction is actor to target author. Edge weight counts distinct captured actions. In/out degree centrality counts unique counterparties, normalized by n - 1. Directed betweenness uses unweighted shortest paths. The activity figure uses a circular layout to keep person labels separate. Figure colors show weakly connected components, not inferred organizational teams.

| Person | In degree | Out degree | Betweenness | Captured actions touching node |
| --- | ---: | ---: | ---: | ---: |
| Thomas Wolf | 0.4444 | 0.1111 | 0.0208 | 6 |
| Julien Chaumond | 0.3333 | 0.0000 | 0.0000 | 5 |
| Remi Fabre | 0.2222 | 0.1111 | 0.0000 | 3 |
| Clem Delangue 🤗 | 0.1111 | 0.3333 | 0.0069 | 5 |
| Lysandre Debut | 0.1111 | 0.0000 | 0.0000 | 1 |
| Ben Burtenshaw | 0.0000 | 0.0000 | 0.0000 | 0 |
| Chun Te Lee | 0.0000 | 0.3333 | 0.0000 | 5 |
| Dana Aubakirova | 0.0000 | 0.1111 | 0.0000 | 1 |
| Pénélope GITTOS | 0.0000 | 0.0000 | 0.0000 | 0 |
| Matthew Douglas | 0.0000 | 0.2222 | 0.0000 | 2 |

## Coverage and limitations

Profiles with unavailable skills in this cohort: 0.

| Section | Profiles with observed entries (all inputs) |
| --- | ---: |
| basic | 10/10 |
| experience | 10/10 |
| education | 10/10 |
| skills | 10/10 |
| interests | 10/10 |
| activity | 10/10 |

Centrality describes this sampled skill graph, not seniority, influence or job performance. Shared skills do not establish a LinkedIn connection, a reporting line or actual collaboration. An organization filter requires explicitly current employment; unknown dates are excluded.

Activity edges require an explicit visible repost/comment/reaction and an identifiable target profile in the cohort. Post reaction totals never identify individual reactors. Interaction edges are kept separately in interactions.json, not mixed into affinity centrality. Activity previews are 90-character excerpts; captured_text retains the body available in the snapshot for interactive details. The source URL identifies the original post, whose complete body may be unavailable.

Missing sections are unavailable, not confirmed empty. All populated sections remain observed_partial because pagination, visibility settings and lazy loading may hide entries. The recent-activity snapshot is not a complete or verified time-bounded activity history.
