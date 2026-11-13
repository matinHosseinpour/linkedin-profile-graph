"""Skill-affinity graph and separately observed directed activity edges."""

import itertools
import textwrap
import unicodedata
from pathlib import Path

import networkx as nx

from .common import dump_json, normalize, profile_url, utc_now
from .interactive import render_explorer


def current_companies(profile):
    return {
        normalize(e["company"])
        for e in profile["experience"]
        if e.get("company") and e.get("is_current") is True
    }


def build_graph(profiles, *, organization=None, threshold=0.25):
    if not 0 < threshold <= 1:
        raise ValueError("The Jaccard threshold must be in (0, 1]")
    ids = [p["id"] for p in profiles]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate profile IDs; merge captures before analysis")
    selected = [
        p for p in profiles if not organization or normalize(organization) in current_companies(p)
    ]
    graph = nx.Graph()
    for profile in selected:
        graph.add_node(
            profile["id"],
            name=profile["basic"]["full_name"],
            headline=profile["basic"]["headline"],
            url=profile["url"],
            skills=sorted({normalize(s["name"]) for s in profile["skills"]}),
            is_synthetic=profile["provenance"]["is_synthetic"],
        )
    for left, right in itertools.combinations(selected, 2):
        ls = set(graph.nodes[left["id"]]["skills"])
        rs = set(graph.nodes[right["id"]]["skills"])
        common = ls & rs
        similarity = len(common) / len(ls | rs) if ls | rs else 0.0
        if common and similarity >= threshold:
            graph.add_edge(
                left["id"],
                right["id"],
                weight=similarity,
                shared_skills=sorted(common),
                relation="inferred_skill_affinity",
            )
    # Betweenness uses unweighted topology: similarities are strengths, not distances.
    degree = nx.degree_centrality(graph) if len(graph) > 1 else dict.fromkeys(graph, 0.0)
    between = nx.betweenness_centrality(graph, normalized=True, weight=None)
    communities = (
        list(nx.community.greedy_modularity_communities(graph, weight="weight"))
        if graph.number_of_edges()
        else [frozenset([node]) for node in graph]
    )
    communities.sort(key=lambda group: (-len(group), sorted(group)))
    for community, members in enumerate(communities):
        for node in sorted(members):
            graph.nodes[node].update(
                degree_centrality=degree[node],
                betweenness_centrality=between[node],
                strength=graph.degree(node, weight="weight"),
                community=community,
            )
    url_to_id = {profile_url(p["url"]): p["id"] for p in selected}
    interactions = []
    for profile in selected:
        for item in profile["activity"]:
            target = item.get("target_profile_url")
            if (
                item["kind"] in {"comment", "reaction", "repost"}
                and target in url_to_id
                and url_to_id[target] != profile["id"]
            ):
                interactions.append(
                    {
                        "source": profile["id"],
                        "target": url_to_id[target],
                        "relation": item["kind"],
                        "activity_id": item["id"],
                        "evidence_url": item["url"],
                        "evidence": item["evidence"],
                    }
                )
    metadata = {
        "generated_at": utc_now(),
        "input_profiles": len(profiles),
        "selected_profiles": len(selected),
        "organization": organization,
        "selection": "explicit current employer, exact normalized name"
        if organization
        else "all inputs",
        "synthetic_profiles": sum(p["provenance"]["is_synthetic"] for p in selected),
        "dataset_kind": "synthetic"
        if selected and all(p["provenance"]["is_synthetic"] for p in selected)
        else "mixed"
        if any(p["provenance"]["is_synthetic"] for p in selected)
        else "observed"
        if selected
        else "empty",
        "jaccard_threshold": threshold,
        "layout_seed": 42,
        "affinity_edges": graph.number_of_edges(),
        "observed_activity_edges": len(interactions),
        "connected_components": nx.number_connected_components(graph),
        "layout_algorithm": "circular" if nx.number_connected_components(graph) > 1 else "spring",
        "communities": len(communities),
        "missing_skills_profiles": sum(not p["skills"] for p in selected),
        "is_linkedin_connection_graph": False,
        "is_organizational_hierarchy": False,
    }
    return graph, interactions, metadata


def render_graph(graph, metadata, destination):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, ax = plt.subplots(figsize=(13, 8), facecolor="#f5f7fb")
    ax.set_facecolor("#f5f7fb")
    prefix = metadata["dataset_kind"].upper()
    graph_title = metadata.get("graph_title", "Skill affinity graph")
    ax.set_title(
        f"{prefix} DATA  |  {graph_title}",
        loc="left",
        fontsize=19,
        pad=30,
        fontweight="bold",
        color="#13243c",
    )
    ax.text(
        0,
        1.015,
        metadata.get(
            "graph_note",
            "Shared visible skills; edges are inferred similarities. "
            "They do not establish LinkedIn connections.",
        ),
        transform=ax.transAxes,
        fontsize=10,
        color="#42536b",
    )
    if graph:
        positions = (
            nx.circular_layout(graph)
            if graph.is_directed() or metadata.get("layout_algorithm") == "circular"
            else nx.spring_layout(graph, seed=42, weight="weight", iterations=150)
        )
        colors = [plt.get_cmap("tab10")(graph.nodes[n]["community"] % 10) for n in graph]
        sizes = [650 + 3200 * graph.nodes[n]["betweenness_centrality"] for n in graph]
        nx.draw_networkx_edges(
            graph,
            positions,
            ax=ax,
            edge_color="#9aaac0",
            alpha=0.55,
            width=[min(5, 1 + 3 * d["weight"]) for _, _, d in graph.edges(data=True)],
            node_size=sizes,
            **(
                {"arrowsize": 20, "connectionstyle": "arc3,rad=0.08"} if graph.is_directed() else {}
            ),
        )
        nx.draw_networkx_nodes(
            graph,
            positions,
            ax=ax,
            node_color=colors,
            node_size=sizes,
            edgecolors="white",
            linewidths=2,
        )
        labels = {
            n: textwrap.fill(
                "".join(
                    c for c in (graph.nodes[n]["name"] or n) if unicodedata.category(c) != "So"
                ).strip(),
                width=16,
            )
            for n in graph
        }
        label_positions = {n: (p[0], p[1] - 0.12) for n, p in positions.items()}
        nx.draw_networkx_labels(
            graph,
            label_positions,
            labels=labels,
            ax=ax,
            font_size=9,
            font_color="#13243c",
            font_weight="bold",
        )
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markersize=10,
                markerfacecolor=plt.get_cmap("tab10")(i % 10),
                label=f"{metadata.get('legend_label', 'Community')} {i + 1}",
            )
            for i in range(metadata["communities"])
        ]
        ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=9)
    else:
        ax.text(
            0.5,
            0.5,
            "No profiles matched the selected cohort",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=16,
        )
    fig.text(
        0.05,
        0.035,
        f"Profiles: {len(graph)}   |   Edges: {graph.number_of_edges()}   |   "
        + (
            "Activity edges are directed   |   "
            if graph.is_directed()
            else f"Jaccard threshold: {metadata['jaccard_threshold']}   |   "
        )
        + "Node size: betweenness",
        fontsize=10,
        color="#42536b",
    )
    ax.margins(0.20)
    ax.axis("off")
    fig.tight_layout(rect=(0.02, 0.07, 0.98, 0.97))
    fig.savefig(destination, dpi=160, facecolor=fig.get_facecolor())
    plt.close(fig)


def observed_activity_graph(graph, interactions):
    observed = nx.DiGraph()
    observed.add_nodes_from((node, dict(attrs)) for node, attrs in graph.nodes(data=True))
    for interaction in interactions:
        left, right = interaction["source"], interaction["target"]
        if not observed.has_edge(left, right):
            observed.add_edge(left, right, weight=0, evidence=[])
        observed[left][right]["weight"] += 1
        observed[left][right]["evidence"].append(interaction)
    between = nx.betweenness_centrality(observed, normalized=True, weight=None)
    incoming = (
        nx.in_degree_centrality(observed) if len(observed) > 1 else dict.fromkeys(observed, 0.0)
    )
    outgoing = (
        nx.out_degree_centrality(observed) if len(observed) > 1 else dict.fromkeys(observed, 0.0)
    )
    components = sorted(nx.weakly_connected_components(observed), key=lambda c: sorted(c))
    for community, component in enumerate(components):
        for node in component:
            observed.nodes[node].pop("degree_centrality", None)
            observed.nodes[node].update(
                betweenness_centrality=between[node],
                in_degree_centrality=incoming[node],
                out_degree_centrality=outgoing[node],
                strength=observed.degree(node, weight="weight"),
                community=community,
            )
    return observed, components


def markdown_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def analysis_findings(graph, observed):
    """Describe leaders within the sample without implying wider influence or missing ties."""
    lines = ["## Findings in this sample", ""]
    if observed.number_of_edges():
        for measure, label in (("in_degree", "incoming"), ("out_degree", "outgoing")):
            degrees = dict(getattr(observed, measure)())
            highest = max(degrees.values())
            leaders = ", ".join(
                markdown_cell(observed.nodes[node]["name"] or node)
                for node in sorted(degrees)
                if degrees[node] == highest
            )
            lines.append(
                f"- Highest observed {label} reach: **{leaders}**, with **{highest}** "
                "distinct counterparties. This is a count within the captured cohort."
            )
        highest_between = max(
            attrs["betweenness_centrality"] for _, attrs in observed.nodes(data=True)
        )
        if highest_between:
            bridges = ", ".join(
                markdown_cell(attrs["name"] or node)
                for node, attrs in sorted(observed.nodes(data=True))
                if attrs["betweenness_centrality"] == highest_between
            )
            lines.append(
                f"- Highest directed betweenness: **{bridges}** ({highest_between:.4f}). "
                "This measures shortest-path brokerage in this observed graph only."
            )
    else:
        lines.append("- No explicit within-cohort interactions were observed in these inputs.")
    lines.append(
        f"- The skill graph has **{graph.number_of_edges()}** edges and "
        f"**{nx.number_connected_components(graph)}** components. Sparse visible skill overlap "
        "limits what can be concluded; missing edges do not establish a lack of real ties."
    )
    return [*lines, ""]


def analyze(profiles, output_dir, *, organization=None, threshold=0.25):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    graph, interactions, metadata = build_graph(
        profiles, organization=organization, threshold=threshold
    )
    nodes = [{"id": node, **attrs} for node, attrs in graph.nodes(data=True)]
    nodes.sort(key=lambda n: (-n["betweenness_centrality"], -n["degree_centrality"], n["id"]))
    artifact = {
        "metadata": metadata,
        "directed": False,
        "nodes": nodes,
        "edges": [
            {"source": left, "target": right, **attrs}
            for left, right, attrs in graph.edges(data=True)
        ],
    }
    dump_json(out / "graph.json", artifact)
    dump_json(
        out / "interactions.json", {"directed": True, "metadata": metadata, "edges": interactions}
    )
    render_graph(graph, metadata, out / "graph.png")
    observed, activity_components = observed_activity_graph(graph, interactions)
    activity_metadata = {
        **metadata,
        "graph_type": "observed_activity",
        "graph_title": "Observed activity graph",
        "graph_note": "Arrows follow visible repost/comment/reaction links within this sample.",
        "communities": len(activity_components),
        "community_method": "weakly connected components",
        "layout_algorithm": "circular",
        "legend_label": "Component",
        "unique_directed_pairs": observed.number_of_edges(),
    }
    activity_nodes = [{"id": node, **attrs} for node, attrs in observed.nodes(data=True)]
    activity_artifact = {
        "metadata": activity_metadata,
        "directed": True,
        "nodes": activity_nodes,
        "edges": [
            {"source": left, "target": right, **attrs}
            for left, right, attrs in observed.edges(data=True)
        ],
    }
    dump_json(out / "activity_graph.json", activity_artifact)
    render_graph(observed, activity_metadata, out / "activity_graph.png")
    render_explorer(profiles, artifact, activity_artifact, out / "interactive.html")
    lines = [
        "# Profile graph analysis",
        "",
        f"Dataset: **{metadata['dataset_kind']}**. Input profiles: **{len(profiles)}**. "
        f"Selected profiles: **{len(graph)}**.",
        "",
        "Open [interactive.html](interactive.html) for the offline explorer: select people, "
        "posts or edges to inspect captured activity, source links and shared-skill evidence. "
        "Search, filter, drag nodes, zoom and export the current view as JSON.",
        "",
        "Synthetic records are fictional fixtures, not extracted LinkedIn members."
        if metadata["synthetic_profiles"]
        else "Only the supplied snapshots are analyzed; "
        "this is not a complete organization census.",
        "",
        f"Organization filter: {markdown_cell(organization) or 'none'}. "
        f"Skill-affinity edges: **{graph.number_of_edges()}**. "
        f"Observed activity edges inside this cohort: **{len(interactions)}**.",
        "",
        *analysis_findings(graph, observed),
        "## Method",
        "",
        "Skill names use Unicode NFKC normalization, case folding and whitespace normalization. "
        "No synonyms, job roles, dates or missing skills are invented. "
        f"Pairs are linked when Jaccard(shared skills / union of skills) >= {threshold}. "
        "Edge weight is that similarity. Missing skill lists produce no affinity edges.",
        "",
        "Degree centrality uses the selected cohort denominator (n - 1); a singleton scores zero. "
        "Normalized betweenness uses unweighted shortest paths. Strength sums similarity weights. "
        "Communities use greedy weighted modularity. "
        f"Skill layout: {metadata['layout_algorithm']}; spring layout seed is 42. "
        "These are graph algorithms; no predictive ML model is trained.",
        "",
        "## Centrality within the observed skill graph",
        "",
        "| Person | Degree | Betweenness | Strength | Community |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for node in nodes:
        lines.append(
            f"| {markdown_cell(node['name'])} | {node['degree_centrality']:.4f} | "
            f"{node['betweenness_centrality']:.4f} | {node['strength']:.4f} | "
            f"{node['community'] + 1} |"
        )
    lines += [
        "",
        "## Centrality within the observed directed activity graph",
        "",
        "Arrow direction is actor to target author. Edge weight counts distinct captured actions. "
        "In/out degree centrality counts unique counterparties, normalized by n - 1. "
        "Directed betweenness uses unweighted shortest paths. "
        "The activity figure uses a circular layout to keep person labels separate. "
        "Figure colors show weakly connected components, not inferred organizational teams.",
        "",
        "| Person | In degree | Out degree | Betweenness | Captured actions touching node |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for node in sorted(activity_nodes, key=lambda n: (-n["in_degree_centrality"], n["id"])):
        lines.append(
            f"| {markdown_cell(node['name'])} | {node['in_degree_centrality']:.4f} | "
            f"{node['out_degree_centrality']:.4f} | {node['betweenness_centrality']:.4f} | "
            f"{node['strength']} |"
        )
    lines += [
        "",
        "## Coverage and limitations",
        "",
        f"Profiles with unavailable skills in this cohort: {metadata['missing_skills_profiles']}.",
        "",
        "| Section | Profiles with observed entries (all inputs) |",
        "| --- | ---: |",
    ]
    for section in ("basic", "experience", "education", "skills", "interests", "activity"):
        count = sum(p["coverage"][section]["items"] > 0 for p in profiles)
        lines.append(f"| {section} | {count}/{len(profiles)} |")
    lines += [
        "",
        "Centrality describes this sampled skill graph, not seniority, influence "
        "or job performance. Shared skills do not establish a LinkedIn connection, "
        "a reporting line or actual collaboration. An organization filter requires "
        "explicitly current employment; unknown dates are excluded.",
        "",
        "Activity edges require an explicit visible repost/comment/reaction and an identifiable "
        "target profile in the cohort. Post reaction totals never identify individual reactors. "
        "Interaction edges are kept separately in interactions.json, "
        "not mixed into affinity centrality. Activity previews are 90-character excerpts; "
        "captured_text retains the body available in the snapshot for interactive details. "
        "The source URL identifies the original post, whose complete body may be unavailable.",
        "",
        "Missing sections are unavailable, not confirmed empty. All populated sections remain "
        "observed_partial because pagination, visibility settings and lazy loading "
        "may hide entries. "
        "The recent-activity snapshot is not a complete or verified time-bounded activity history.",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return artifact
