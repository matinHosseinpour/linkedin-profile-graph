"""Build a portable, offline explorer from selected profiles and evidence edges."""

import json
import math
from pathlib import Path

import networkx as nx

from .common import profile_url


def explorer_data(profiles, affinity, activity):
    selected_ids = {node["id"] for node in affinity["nodes"]}
    selected = [profile for profile in profiles if profile["id"] in selected_ids]
    by_url = {profile_url(profile["url"]): profile["id"] for profile in selected}
    actions = []
    posts = {}
    for profile in selected:
        for item in profile["activity"]:
            try:
                target_id = by_url.get(profile_url(item["target_profile_url"]))
            except (ValueError, TypeError, KeyError):
                target_id = None
            action_id = f"action-{len(actions)}"
            # Missing post URLs must never merge unrelated observations across people.
            post_id = "post:" + (item.get("url") or f"{profile['id']}:{item['id']}")
            action = {
                **item,
                "key": action_id,
                "actor_id": profile["id"],
                "target_id": target_id,
                "post_id": post_id,
                "captured_at": profile["provenance"].get("collected_at"),
            }
            actions.append(action)
            posts.setdefault(post_id, {"id": post_id, "action_ids": []})["action_ids"].append(
                action_id
            )
    layouts = {}
    for mode, edges in (
        ("people", activity["edges"]),
        ("skills", affinity["edges"]),
        ("posts", [{"source": a["actor_id"], "target": a["post_id"]} for a in actions]),
    ):
        graph = nx.Graph()
        graph.add_nodes_from(sorted(selected_ids))
        if mode == "posts":
            graph.add_nodes_from(posts)
        graph.add_edges_from((edge["source"], edge["target"]) for edge in edges)
        if mode == "posts" and graph:
            people_positions = nx.circular_layout(sorted(selected_ids))
            initial = {
                node: [float(point[0]) * 850, float(point[1]) * 650]
                for node, point in people_positions.items()
            }
            for index, post in enumerate(posts):
                actors = list(graph.neighbors(post))
                angle = index * math.pi * (3 - math.sqrt(5))
                initial[post] = [
                    sum(initial[actor][0] for actor in actors) / len(actors)
                    + 140 * math.cos(angle),
                    sum(initial[actor][1] for actor in actors) / len(actors)
                    + 140 * math.sin(angle),
                ]
            positions = nx.spring_layout(
                graph, pos=initial, fixed=sorted(selected_ids), k=110, iterations=180, seed=42
            )
        else:
            # A sparse graph's isolated nodes otherwise squash its connected core.
            positions = {
                node: [float(point[0]) * 420, float(point[1]) * 300]
                for node, point in nx.circular_layout(graph).items()
            }
        layouts[mode] = {
            node: [round(float(point[0]), 3), round(float(point[1]), 3)]
            for node, point in positions.items()
        }
    return {
        "schema_version": "1.0",
        "metadata": affinity["metadata"],
        "profiles": selected,
        "actions": actions,
        "posts": list(posts.values()),
        "affinity": affinity,
        "activity": activity,
        "layouts": layouts,
    }


def render_explorer(profiles, affinity, activity, destination):
    data = explorer_data(profiles, affinity, activity)
    # Script tags terminate even inside JSON strings; escape all HTML delimiters.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    for char, escaped in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        payload = payload.replace(char, escaped)
    assets = Path(__file__).parent
    html = (assets / "explorer.html").read_text(encoding="utf-8")
    html = html.replace("/* EXPLORER_STYLE */", (assets / "explorer.css").read_text())
    html = html.replace("/* EXPLORER_SCRIPT */", (assets / "explorer.js").read_text())
    html = html.replace("EXPLORER_DATA", payload)
    Path(destination).write_text(html, encoding="utf-8")
    return data
