from __future__ import annotations

import math
from typing import Iterable, Sequence

from manim import *
from manim_slides import Slide


config.background_color = ManimColor("#071321")
config.frame_width = 16
config.frame_height = 9
config.pixel_width = 1920
config.pixel_height = 1080
config.frame_rate = 60


DEEP_NAVY = "#071321"
PANEL = "#0D1B2A"
PANEL_2 = "#10243A"
BLUE = "#3B82F6"
CYAN = "#22D3EE"
PURPLE = "#A78BFA"
AMBER = "#FBBF24"
RED = "#FB7185"
GREEN = "#34D399"
GRAY = "#94A3B8"
SLATE = "#475569"
TEAL = "#2DD4BF"
WHITE = "#EAF2FF"
MUTED = "#AAB7C8"

FONT = "Liberation Mono"
LOG_FONT = "Liberation Mono"
TITLE_SIZE = 42
LABEL_SIZE = 26
SMALL_SIZE = 22
CAPTION_SIZE = 28
STROKE = 3


def make_caption(text: str) -> Text:
    caption = Text(text, font=FONT, font_size=CAPTION_SIZE, color=WHITE)
    caption.to_edge(DOWN, buff=0.38)
    return caption


def make_spaced_label(left: str, right: str, color: str, font_size: int = 20) -> VGroup:
    return VGroup(
        Text(left, font=FONT, font_size=font_size, color=color),
        Text(right, font=FONT, font_size=font_size, color=color),
    ).arrange(RIGHT, buff=0.12, aligned_edge=DOWN)


def make_chapter_title(number: int, title: str, subtitle: str | None = None) -> VGroup:
    n = Text(f"{number:02d}", font=FONT, font_size=30, color=CYAN, weight=BOLD)
    bar = Line(LEFT, RIGHT, color=CYAN, stroke_width=5).set_width(0.9)
    main = Text(title, font=FONT, font_size=TITLE_SIZE, color=WHITE, weight=BOLD)
    group = VGroup(n, bar, main).arrange(RIGHT, buff=0.28)
    if subtitle:
        sub = Text(subtitle, font=FONT, font_size=24, color=MUTED)
        return VGroup(group, sub).arrange(DOWN, aligned_edge=LEFT, buff=0.18)
    return group


def make_service_box(label: str, color: str = BLUE, width: float = 2.2, font_size: int = LABEL_SIZE) -> VGroup:
    box = RoundedRectangle(
        width=width,
        height=0.72,
        corner_radius=0.12,
        stroke_color=color,
        fill_color=PANEL,
        fill_opacity=0.92,
        stroke_width=STROKE,
    )
    text = Text(label, font=FONT, font_size=font_size, color=WHITE)
    if text.width > width - 0.28:
        text.scale_to_fit_width(width - 0.28)
    return VGroup(box, text)


def make_storage_cylinder(label: str, width: float = 2.2, height: float = 1.55) -> VGroup:
    body = Rectangle(
        width=width,
        height=height,
        stroke_color=GRAY,
        fill_color="#152033",
        fill_opacity=0.95,
        stroke_width=STROKE,
    )
    top = Ellipse(width=width, height=0.38, stroke_color=GRAY, fill_color="#1B2B44", fill_opacity=1, stroke_width=STROKE)
    bottom = Ellipse(width=width, height=0.38, stroke_color=GRAY, fill_color="#101A2C", fill_opacity=1, stroke_width=STROKE)
    top.move_to(body.get_top())
    bottom.move_to(body.get_bottom())
    text = Text(label, font=FONT, font_size=SMALL_SIZE, color=WHITE)
    text.move_to(body.get_center())
    return VGroup(body, bottom, top, text)


def make_event_card(title: str, fields: Sequence[tuple[str, str]], color: str = BLUE, width: float = 4.55) -> VGroup:
    height = 0.72 + 0.35 * max(1, len(fields))
    rect = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.16,
        stroke_color=color,
        fill_color=PANEL,
        fill_opacity=0.96,
        stroke_width=STROKE,
    )
    title_text = Text(title, font=FONT, font_size=24, color=color, weight=BOLD)
    lines = VGroup()
    for key, value in fields:
        key_t = Text(f"{key:<11}", font=FONT, font_size=18, color=MUTED)
        value_t = Text(value, font=FONT, font_size=18, color=WHITE)
        row = VGroup(key_t, value_t).arrange(RIGHT, buff=0.18)
        lines.add(row)
    lines.arrange(DOWN, aligned_edge=LEFT, buff=0.09)
    content = VGroup(title_text, lines).arrange(DOWN, aligned_edge=LEFT, buff=0.22)
    content.move_to(rect.get_center()).align_to(rect, LEFT).shift(RIGHT * 0.24)
    return VGroup(rect, content)


def make_graph_node(label: str, color: str, radius: float = 0.28, seed: bool = False) -> VGroup:
    node = Circle(
        radius=radius,
        stroke_color=color,
        fill_color=PANEL_2,
        fill_opacity=1.0,
        stroke_width=5 if seed else STROKE,
    )
    glow = Circle(radius=radius * 1.55, stroke_color=color, fill_opacity=0, stroke_opacity=0.22, stroke_width=8)
    text = Text(label, font=FONT, font_size=18, color=WHITE, weight=BOLD if seed else NORMAL)
    glow.set_z_index(1)
    node.set_z_index(2)
    text.set_z_index(3)
    return VGroup(glow, node, text)


def graph_edge_between(source: VGroup, target: VGroup, color: str, stroke_width: float = 5, dashed: bool = False) -> VMobject:
    """Draw an edge from visible node boundary to visible node boundary."""
    source_circle = source[1]
    target_circle = target[1]
    direction = target_circle.get_center() - source_circle.get_center()
    if np.linalg.norm(direction) == 0:
        direction = RIGHT
    start = source_circle.get_boundary_point(direction)
    end = target_circle.get_boundary_point(-direction)
    edge: VMobject = Line(start, end, color=color, stroke_width=stroke_width)
    edge.set_z_index(0)
    if dashed:
        edge = DashedVMobject(edge, num_dashes=12)
        edge.set_z_index(0)
    return edge


def make_arrow(start, end, color: str = CYAN, dashed: bool = False) -> VMobject:
    arrow = Arrow(start, end, color=color, buff=0.14, stroke_width=5, max_tip_length_to_length_ratio=0.12)
    if dashed:
        return DashedVMobject(arrow, num_dashes=12)
    return arrow


def pulse(mobject: Mobject, color: str = CYAN) -> AnimationGroup:
    return AnimationGroup(
        Indicate(mobject, color=color, scale_factor=1.08),
        Flash(mobject, color=color, line_length=0.18, num_lines=14, flash_radius=0.55),
    )


class RCACopilotExplainerSlides(Slide):
    """Interactive slide presentation for the OpenStack RCA Copilot explainer."""

    def construct(self) -> None:
        self.camera.background_color = ManimColor(DEEP_NAVY)
        self.intro()
        self.problem()
        self.raw_capture()
        self.parsing()
        self.events_to_graph()
        self.graph_safety()
        self.incident_subgraph()
        self.enrichment()
        self.horizon_view()
        self.future_ai()
        self.final_summary()

    def swap_caption(self, old: Mobject | None, text: str) -> Text:
        new = make_caption(text)
        if old is None:
            self.play(FadeIn(new, shift=UP * 0.15), run_time=0.45)
        else:
            self.play(Transform(old, new), run_time=0.45)
            return old  # type: ignore[return-value]
        return new

    def clear_scene(self) -> None:
        self.play(*[FadeOut(mob) for mob in self.mobjects], run_time=0.65)

    def intro(self) -> None:
        title = Text("OpenStack RCA Copilot", font=FONT, font_size=58, color=WHITE, weight=BOLD)
        subtitle = Text("from noisy logs to explainable investigation evidence", font=FONT, font_size=30, color=MUTED)
        chain = Text("Logs  →  Events  →  Graph  →  Evidence  →  Investigation", font=FONT, font_size=30, color=CYAN)
        group = VGroup(title, subtitle, chain).arrange(DOWN, buff=0.38)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.8)
        self.next_slide()
        self.play(FadeIn(subtitle), Write(chain), run_time=1.25)
        self.next_slide()
        self.wait(1.2)
        self.play(group.animate.scale(0.72).to_edge(UP, buff=0.45), run_time=0.8)
        self.play(FadeOut(group), run_time=0.45)

    # Chapter 1: the problem.
    def problem(self) -> None:
        title = make_chapter_title(1, "The problem", "important failures hide in ordinary log noise").to_edge(UP, buff=0.35)
        services = VGroup(*[make_service_box(s) for s in ["Nova", "Neutron", "Keystone", "Placement"]]).arrange(DOWN, buff=0.28)
        services.to_edge(LEFT, buff=1.0).shift(DOWN * 0.25)
        stream_box = RoundedRectangle(width=8.9, height=5.5, corner_radius=0.18, stroke_color=SLATE, fill_color=PANEL, fill_opacity=0.72)
        stream_box.to_edge(RIGHT, buff=0.75).shift(DOWN * 0.25)
        logs = VGroup()
        samples = [
            "INFO nova.scheduler selected host compute-02",
            "DEBUG neutron.agent heartbeat ok",
            "INFO keystone token validated",
            "WARNING placement allocation retry",
            "INFO nova.compute spawning instance",
            "ERROR nova.compute Build failed for instance 48f...",
            "DEBUG oslo.messaging ack delivery",
            "INFO neutron.port binding updated",
        ]
        for line in samples:
            color = RED if line.startswith("ERROR") else AMBER if line.startswith("WARNING") else MUTED
            logs.add(Text(line, font=LOG_FONT, font_size=20, color=color))
        logs.arrange(DOWN, aligned_edge=LEFT, buff=0.24).move_to(stream_box.get_center()).align_to(stream_box, LEFT).shift(RIGHT * 0.35)
        arrows = VGroup(*[make_arrow(s.get_right(), stream_box.get_left() + RIGHT * 0.15, CYAN) for s in services])
        caption = make_caption("OpenStack failures hide inside thousands of small log events.")
        self.play(FadeIn(title), LaggedStart(*[FadeIn(s, shift=RIGHT * 0.18) for s in services], lag_ratio=0.08), run_time=1.1)
        self.next_slide()
        self.play(Create(stream_box), LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.07), run_time=1.0)
        self.play(LaggedStart(*[FadeIn(line, shift=LEFT * 0.15) for line in logs], lag_ratio=0.08), FadeIn(caption), run_time=1.6)
        self.next_slide()
        self.play(pulse(logs[5], RED), run_time=1.0)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 2: raw evidence capture.
    def raw_capture(self) -> None:
        title = make_chapter_title(2, "Raw evidence capture", "preserve first, interpret later").to_edge(UP, buff=0.35)
        journal = make_event_card("journald JSON", [("timestamp", "10:14:09Z"), ("unit", "nova-compute"), ("cursor", "s=8f12...")], GRAY, width=3.7)
        journal.move_to(LEFT * 5.1 + UP * 0.5)
        collector = make_service_box("collector", CYAN).move_to(LEFT * 2.2 + UP * 0.5)
        api = make_service_box("FastAPI ingestion", BLUE, width=2.75, font_size=24).move_to(RIGHT * 0.9 + UP * 0.5)
        raw = make_storage_cylinder("raw_logs").move_to(RIGHT * 4.6 + UP * 0.5)
        checkpoint = VGroup(
            Circle(radius=0.23, color=GREEN, fill_color=GREEN, fill_opacity=0.18, stroke_width=3),
            Text("✓", font=FONT, font_size=24, color=GREEN),
            Text("checkpoint", font=FONT, font_size=20, color=MUTED).next_to(Circle(radius=0.23), RIGHT, buff=0.18),
        )
        checkpoint.arrange(RIGHT, buff=0.16).next_to(raw, DOWN, buff=0.45)
        arrows = VGroup(
            make_arrow(journal.get_right(), collector.get_left(), CYAN),
            make_arrow(collector.get_right(), api.get_left(), CYAN),
            make_arrow(api.get_right(), raw.get_left(), CYAN),
        )
        caption = make_caption("First, we preserve raw evidence without guessing.")
        self.play(FadeIn(title), FadeIn(journal), run_time=0.8)
        self.next_slide()
        self.play(GrowArrow(arrows[0]), FadeIn(collector), run_time=0.65)
        self.play(GrowArrow(arrows[1]), FadeIn(api), run_time=0.65)
        self.play(GrowArrow(arrows[2]), FadeIn(raw), FadeIn(checkpoint), FadeIn(caption), run_time=0.9)
        self.next_slide()
        self.play(pulse(raw, GREEN), run_time=0.9)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 3: parsing.
    def parsing(self) -> None:
        title = make_chapter_title(3, "Parsing", "messy text becomes searchable structure").to_edge(UP, buff=0.35)
        raw_line = Text("ERROR nova.compute.manager Build failed: instance 48f...", font=FONT, font_size=28, color=RED)
        raw_shell = RoundedRectangle(width=12.2, height=0.85, corner_radius=0.12, stroke_color=RED, fill_color=PANEL, fill_opacity=0.95)
        raw_group = VGroup(raw_shell, raw_line).move_to(UP * 2.35)
        parser = make_service_box("parser-worker", PURPLE, width=2.85, font_size=25).move_to(LEFT * 4.7 + UP * 0.55)
        parsed_db = make_storage_cylinder("parsed_logs", width=2.15, height=1.35).move_to(RIGHT * 4.8 + UP * 0.55)
        fields = [
            ("level", "ERROR"),
            ("service", "nova-compute"),
            ("module", "nova.compute.manager"),
            ("request_id", "req-7d31..."),
            ("resource_id", "instance 48f..."),
            ("message", "Build failed..."),
        ]
        card = make_event_card("parsed event", fields, RED, width=4.8).move_to(DOWN * 0.9)
        node = make_graph_node("E", RED, radius=0.36, seed=False).move_to(RIGHT * 0.2 + DOWN * 0.85)
        arrows = VGroup(
            make_arrow(raw_group.get_bottom(), parser.get_top(), PURPLE),
            make_arrow(parser.get_right(), parsed_db.get_left(), PURPLE),
            make_arrow(parser.get_bottom(), card.get_left() + LEFT * 0.1, PURPLE),
        )
        lineage = Text("raw_logs  →  parser-worker  →  parsed_logs", font=FONT, font_size=25, color=CYAN).to_edge(DOWN, buff=0.94)
        caption = make_caption("The parser turns messy text into searchable event objects.")
        self.play(FadeIn(title), FadeIn(raw_group), run_time=0.8)
        self.next_slide()
        self.play(FadeIn(parser), GrowArrow(arrows[0]), run_time=0.65)
        self.play(FadeIn(card, shift=UP * 0.2), GrowArrow(arrows[2]), run_time=1.0)
        self.play(FadeIn(parsed_db), GrowArrow(arrows[1]), Write(lineage), FadeIn(caption), run_time=1.0)
        self.next_slide()
        self.play(Transform(card, node), FadeOut(raw_group), FadeOut(parser), FadeOut(parsed_db), FadeOut(arrows), FadeOut(lineage), run_time=1.1)
        self.play(pulse(card, RED), run_time=0.85)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 4: events become a graph.
    def events_to_graph(self) -> None:
        title = make_chapter_title(4, "Events become a graph", "relations form only when evidence is shared").to_edge(UP, buff=0.35)
        positions = [LEFT * 4.7 + UP * 1.3, LEFT * 2.2 + UP * 1.55, LEFT * 0.1 + UP * 0.55, RIGHT * 2.0 + UP * 1.4, RIGHT * 4.3 + UP * 0.1, LEFT * 2.7 + DOWN * 1.55, RIGHT * 0.25 + DOWN * 1.55]
        specs = [("I", BLUE), ("W", AMBER), ("E", RED), ("I", BLUE), ("D", GRAY), ("W", AMBER), ("E", RED)]
        nodes = VGroup(*[make_graph_node(label, color).move_to(pos) for (label, color), pos in zip(specs, positions)])
        edges = VGroup(
            graph_edge_between(nodes[0], nodes[1], PURPLE),
            graph_edge_between(nodes[1], nodes[2], PURPLE),
            graph_edge_between(nodes[2], nodes[3], TEAL),
            graph_edge_between(nodes[3], nodes[4], TEAL),
            graph_edge_between(nodes[2], nodes[5], PURPLE),
            graph_edge_between(nodes[5], nodes[6], TEAL),
        )
        legend = VGroup(
            Text("ERROR event", font=FONT, font_size=20, color=RED),
            Text("WARNING event", font=FONT, font_size=20, color=AMBER),
            Text("INFO event", font=FONT, font_size=20, color=BLUE),
            make_spaced_label("same", "request_id", PURPLE),
            make_spaced_label("shared", "resource_id", TEAL),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.18).to_edge(RIGHT, buff=0.55).shift(DOWN * 1.35)
        rule1 = Text("same request_id -> strong correlation", font=FONT, font_size=24, color=PURPLE).move_to(LEFT * 3.85 + DOWN * 3.08)
        rule2 = Text("shared resource_id -> resource correlation", font=FONT, font_size=24, color=TEAL).move_to(RIGHT * 3.35 + DOWN * 3.08)
        caption = make_caption("Edges mean correlation, not proven causality.")
        self.play(FadeIn(title), LaggedStart(*[FadeIn(n, scale=0.8) for n in nodes], lag_ratio=0.08), run_time=1.1)
        self.next_slide()
        self.play(LaggedStart(*[Create(e) for e in edges], lag_ratio=0.12), FadeIn(legend), run_time=1.35)
        self.next_slide()
        self.play(FadeIn(rule1), FadeIn(rule2), FadeIn(caption), run_time=0.8)
        self.play(pulse(edges[1], PURPLE), pulse(edges[2], TEAL), run_time=1.0)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 5: avoiding graph explosion.
    def graph_safety(self) -> None:
        title = make_chapter_title(5, "Avoiding graph explosion", "bounded rules keep the graph useful").to_edge(UP, buff=0.35)
        circle_points = [np.array([1.55 * math.cos(i * TAU / 9), 1.35 * math.sin(i * TAU / 9), 0]) + LEFT * 4.0 + UP * 0.3 for i in range(9)]
        messy_nodes = VGroup(*[make_graph_node("", AMBER, radius=0.18).move_to(p) for p in circle_points])
        messy_edges = VGroup(*[graph_edge_between(messy_nodes[i], messy_nodes[j], SLATE, stroke_width=1.6) for i in range(9) for j in range(i + 1, 9)])
        for edge in messy_edges:
            edge.set_opacity(0.5)
        messy_label = Text("naive: everything connects", font=FONT, font_size=20, color=AMBER).next_to(messy_nodes, DOWN, buff=0.42)
        clean_positions = [RIGHT * 0.55 + RIGHT * i * 0.72 + UP * (0.36 * math.sin(i)) + UP * 0.55 for i in range(7)]
        clean_nodes = VGroup(*[make_graph_node("", BLUE if i % 3 else RED, radius=0.2).move_to(clean_positions[i]) for i in range(7)])
        clean_edges = VGroup(*[graph_edge_between(clean_nodes[i], clean_nodes[i + 1], CYAN, stroke_width=4) for i in range(6)])
        clean_label = Text("implemented: chronological and bounded", font=FONT, font_size=20, color=GREEN).next_to(clean_nodes, DOWN, buff=0.46)
        rules = VGroup(
            Text("consecutive edges only", font=FONT, font_size=20, color=WHITE),
            Text("periodic groups skipped", font=FONT, font_size=20, color=WHITE),
            Text("oversized groups bounded", font=FONT, font_size=20, color=WHITE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.22).move_to(RIGHT * 3.65 + DOWN * 1.75)
        caption = make_caption("The graph stays useful because it is bounded and chronological.")
        self.play(FadeIn(title), FadeIn(messy_nodes), LaggedStart(*[Create(e) for e in messy_edges], lag_ratio=0.01), FadeIn(messy_label), run_time=1.4)
        self.next_slide()
        self.play(messy_edges.animate.set_opacity(0.15), messy_nodes.animate.set_opacity(0.25), messy_label.animate.set_opacity(0.35), run_time=0.6)
        self.play(FadeIn(clean_nodes), LaggedStart(*[Create(e) for e in clean_edges], lag_ratio=0.12), FadeIn(clean_label), FadeIn(rules), FadeIn(caption), run_time=1.25)
        self.next_slide()
        self.play(pulse(clean_edges, GREEN), run_time=0.8)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 6: incident seed and bounded subgraph.
    def incident_subgraph(self) -> None:
        title = make_chapter_title(6, "Incident construction", "start from a suspicious event, then bound the search").to_edge(UP, buff=0.35)
        positions = [LEFT * 4 + UP * 1.4, LEFT * 2.5 + UP * 0.8, LEFT * 1.0 + UP * 1.45, ORIGIN + DOWN * 0.05, RIGHT * 1.6 + UP * 0.7, RIGHT * 3.25 + UP * 1.45, LEFT * 2 + DOWN * 1.35, RIGHT * 1.2 + DOWN * 1.55, RIGHT * 3.8 + DOWN * 0.75]
        colors = [BLUE, AMBER, BLUE, RED, AMBER, BLUE, GRAY, TEAL, GRAY]
        nodes = VGroup(*[make_graph_node("S" if i == 3 else "", c, radius=0.25, seed=(i == 3)).move_to(p) for i, (p, c) in enumerate(zip(positions, colors))])
        edge_pairs = [(0, 1), (1, 3), (2, 3), (3, 4), (4, 5), (3, 6), (3, 7), (7, 8)]
        edges = VGroup(*[
            graph_edge_between(nodes[a], nodes[b], PURPLE if i % 2 else TEAL, stroke_width=4)
            for i, (a, b) in enumerate(edge_pairs)
        ])
        search = Circle(radius=0.4, color=CYAN, stroke_width=5).move_to(nodes[3])
        boundary = Circle(radius=2.65, color=CYAN, stroke_width=3).move_to(nodes[3])
        boundary.set_stroke(opacity=0.55)
        limits = VGroup(
            Text("max depth", font=FONT, font_size=24, color=CYAN),
            Text("time window", font=FONT, font_size=24, color=CYAN),
            Text("max events", font=FONT, font_size=24, color=CYAN),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2).to_edge(RIGHT, buff=1.0).shift(DOWN * 1.0)
        package = make_event_card("incident evidence package", [("seed", "ERROR event"), ("scope", "bounded subgraph"), ("stored", "incidents")], GREEN, width=4.0).move_to(DOWN * 2.25)
        caption = make_caption("An incident is not the whole log history. It is a bounded evidence subgraph.")
        self.play(FadeIn(title), FadeIn(nodes), LaggedStart(*[Create(e) for e in edges], lag_ratio=0.08), run_time=1.2)
        self.next_slide()
        self.play(pulse(nodes[3], RED), FadeIn(Text("seed event", font=FONT, font_size=24, color=RED).next_to(nodes[3], UP, buff=0.35)), run_time=0.9)
        self.next_slide()
        self.play(Create(search), search.animate.scale(6.6), Create(boundary), FadeIn(limits), FadeIn(caption), run_time=1.35)
        self.next_slide()
        selected = VGroup(nodes[1], nodes[2], nodes[3], nodes[4], nodes[6], nodes[7], edges[1], edges[2], edges[3], edges[5], edges[6])
        self.play(Transform(selected.copy(), package), FadeIn(package), run_time=1.0)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 7: enrichment.
    def enrichment(self) -> None:
        title = make_chapter_title(7, "Deterministic enrichment", "build the evidence package before AI").to_edge(UP, buff=0.35)
        source = make_event_card("bounded subgraph", [("events", "37"), ("edges", "52"), ("seed", "nova ERROR")], PURPLE, width=3.7).move_to(LEFT * 4.9 + UP * 0.55)
        enrich = make_service_box("enrichment-worker", TEAL, width=3.0, font_size=24).move_to(LEFT * 1.1 + UP * 0.55)
        cards = VGroup(
            make_event_card("timeline", [("ordered", "event sequence")], TEAL, width=2.55),
            make_event_card("services", [("nova", "neutron")], BLUE, width=2.55),
            make_event_card("resources", [("instance", "48f...")], GREEN, width=2.55),
            make_event_card("summary", [("type", "deterministic")], AMBER, width=2.55),
        ).arrange_in_grid(rows=2, cols=2, buff=0.28).move_to(RIGHT * 3.6 + UP * 0.15)
        arrow1 = make_arrow(source.get_right(), enrich.get_left(), TEAL)
        arrow2 = make_arrow(enrich.get_right(), cards.get_left(), TEAL)
        caption = make_caption("Before AI, the system builds a structured evidence package.")
        self.play(FadeIn(title), FadeIn(source), run_time=0.7)
        self.next_slide()
        self.play(FadeIn(enrich), GrowArrow(arrow1), run_time=0.6)
        self.play(GrowArrow(arrow2), LaggedStart(*[FadeIn(c, shift=UP * 0.1) for c in cards], lag_ratio=0.12), FadeIn(caption), run_time=1.2)
        self.next_slide()
        self.play(pulse(cards, GREEN), run_time=0.85)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 8: Horizon investigation view.
    def horizon_view(self) -> None:
        title = make_chapter_title(8, "Horizon investigation", "operators inspect the bounded evidence").to_edge(UP, buff=0.35)
        dashboard = RoundedRectangle(width=13.4, height=6.2, corner_radius=0.18, stroke_color=BLUE, fill_color="#0B1728", fill_opacity=0.95, stroke_width=3).shift(DOWN * 0.1)
        sidebar = RoundedRectangle(width=2.6, height=5.5, corner_radius=0.12, stroke_color=SLATE, fill_color=PANEL_2, fill_opacity=0.9).move_to(dashboard.get_left() + RIGHT * 1.55)
        graph_panel = RoundedRectangle(width=4.6, height=3.2, corner_radius=0.12, stroke_color=PURPLE, fill_color=PANEL, fill_opacity=0.82).move_to(LEFT * 0.3 + UP * 0.85)
        timeline = RoundedRectangle(width=4.6, height=1.75, corner_radius=0.12, stroke_color=TEAL, fill_color=PANEL, fill_opacity=0.82).next_to(graph_panel, DOWN, buff=0.28)
        details = RoundedRectangle(width=3.9, height=5.25, corner_radius=0.12, stroke_color=GREEN, fill_color=PANEL, fill_opacity=0.82).move_to(RIGHT * 4.45 + DOWN * 0.05)
        labels = VGroup(
            Text("Incident list", font=FONT, font_size=22, color=WHITE).move_to(sidebar.get_top() + DOWN * 0.35),
            Text("Graph view", font=FONT, font_size=22, color=PURPLE).move_to(graph_panel.get_top() + DOWN * 0.3),
            Text("Timeline", font=FONT, font_size=22, color=TEAL).move_to(timeline.get_top() + DOWN * 0.3),
            Text("Event details", font=FONT, font_size=22, color=GREEN).move_to(details.get_top() + DOWN * 0.35),
        )
        mini_nodes = VGroup(*[make_graph_node("", c, radius=0.14).move_to(graph_panel.get_center() + v) for c, v in [(RED, LEFT * 1.2), (AMBER, LEFT * 0.25 + UP * 0.45), (BLUE, RIGHT * 0.85), (TEAL, RIGHT * 0.2 + DOWN * 0.65)]])
        mini_edges = VGroup(
            graph_edge_between(mini_nodes[0], mini_nodes[1], PURPLE, stroke_width=3),
            graph_edge_between(mini_nodes[1], mini_nodes[2], TEAL, stroke_width=3),
            graph_edge_between(mini_nodes[1], mini_nodes[3], PURPLE, stroke_width=3),
        )
        ticks = VGroup(*[Line(UP * 0.18, DOWN * 0.18, color=TEAL, stroke_width=4).move_to(timeline.get_left() + RIGHT * (0.75 + i * 0.75) + DOWN * 0.3) for i in range(5)])
        detail_text = VGroup(
            Text("service: nova-compute", font=FONT, font_size=20, color=WHITE),
            Text("resource: instance 48f...", font=FONT, font_size=20, color=WHITE),
            Text("evidence summary", font=FONT, font_size=20, color=GREEN),
            Text("future AI panel", font=FONT, font_size=20, color=MUTED),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25).move_to(details.get_center()).align_to(details, LEFT).shift(RIGHT * 0.32)
        caption = make_caption("Click a node or timeline event; the evidence view follows the same incident.")
        self.play(FadeIn(title), Create(dashboard), FadeIn(sidebar), FadeIn(graph_panel), FadeIn(timeline), FadeIn(details), FadeIn(labels), run_time=1.1)
        self.next_slide()
        self.play(FadeIn(mini_nodes), Create(mini_edges), FadeIn(ticks), FadeIn(detail_text), FadeIn(caption), run_time=1.1)
        self.next_slide()
        self.play(pulse(mini_nodes[0], RED), pulse(ticks[2], TEAL), detail_text.animate.set_color(WHITE), run_time=1.0)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 9: future AI/RAG layer.
    def future_ai(self) -> None:
        title = make_chapter_title(9, "Future AI/RAG layer", "replaceable AI, evidence as source of truth").to_edge(UP, buff=0.35)
        evidence = make_event_card("evidence package", [("timeline", "yes"), ("graph", "bounded"), ("summary", "deterministic")], GREEN, width=3.25).move_to(LEFT * 5.55 + UP * 0.55).scale(0.9)
        steps = VGroup(
            make_service_box("embeddings", TEAL, width=1.82, font_size=23),
            make_service_box("retrieval", CYAN, width=1.82, font_size=23),
            make_service_box("reranking", PURPLE, width=1.82, font_size=23),
            make_service_box("LLM provider", BLUE, width=2.1, font_size=22),
        ).arrange(RIGHT, buff=0.34).move_to(UP * 0.7 + RIGHT * 1.95)
        explanation = make_event_card("grounded RCA explanation", [("input", "structured evidence"), ("status", "future capability")], AMBER, width=3.7).move_to(RIGHT * 3.65 + DOWN * 1.75).scale(0.88)
        future_box = SurroundingRectangle(VGroup(steps, explanation), color=GRAY, stroke_width=3, buff=0.35, corner_radius=0.18)
        future_box = DashedVMobject(future_box, num_dashes=48)
        future_label = Text("future / provider-agnostic", font=FONT, font_size=24, color=GRAY).next_to(future_box, UP, buff=0.12)
        providers = VGroup(*[Text(p, font=FONT, font_size=18, color=MUTED) for p in ["Ollama", "OpenAI-compatible", "Gemini", "Claude", "Custom HTTP"]]).arrange(DOWN, aligned_edge=LEFT, buff=0.08)
        providers.next_to(steps[-1], DOWN, buff=0.35).align_to(steps[-1], LEFT)
        arrows = VGroup(make_arrow(evidence.get_right(), steps[0].get_left(), TEAL, dashed=True))
        for left, right in zip(steps[:-1], steps[1:]):
            arrows.add(make_arrow(left.get_right(), right.get_left(), CYAN, dashed=True))
        arrows.add(make_arrow(steps[-1].get_bottom(), explanation.get_top(), AMBER, dashed=True))
        caption = make_caption("AI is replaceable. Evidence stays the source of truth.")
        self.play(FadeIn(title), FadeIn(evidence), Create(future_box), FadeIn(future_label), run_time=0.9)
        self.next_slide()
        self.play(LaggedStart(*[FadeIn(s, shift=RIGHT * 0.1) for s in steps], lag_ratio=0.15), LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12), run_time=1.3)
        self.next_slide()
        self.play(FadeIn(providers), FadeIn(explanation), FadeIn(caption), run_time=0.9)
        self.next_slide()
        self.play(pulse(evidence, GREEN), pulse(explanation, AMBER), run_time=1.0)
        self.next_slide()
        self.wait(3.5)
        self.clear_scene()

    # Chapter 10: final recap.
    def final_summary(self) -> None:
        title = Text("RCA Copilot pipeline", font=FONT, font_size=48, color=WHITE, weight=BOLD).to_edge(UP, buff=0.45)
        labels = ["Logs", "Structured\nEvents", "Correlation\nGraph", "Incident\nEvidence", "Horizon\nInvestigation", "Future\nGrounded\nAI"]
        colors = [GRAY, BLUE, PURPLE, GREEN, CYAN, AMBER]
        nodes = VGroup(*[
            RoundedRectangle(width=2.0, height=1.15, corner_radius=0.16, stroke_color=c, fill_color=PANEL, fill_opacity=0.96, stroke_width=3)
            for c in colors
        ]).arrange(RIGHT, buff=0.32).move_to(UP * 0.65)
        texts = VGroup(*[Text(t, font=FONT, font_size=20, color=WHITE).move_to(n.get_center()) for t, n in zip(labels, nodes)])
        arrows = VGroup(*[make_arrow(nodes[i].get_right(), nodes[i + 1].get_left(), CYAN if i < 4 else AMBER, dashed=(i == 4)) for i in range(len(nodes) - 1)])
        final = Text("Noisy cloud logs become structured, explainable investigation evidence.", font=FONT, font_size=29, color=WHITE)
        final.scale_to_fit_width(14.6)
        final.to_edge(DOWN, buff=0.85)
        self.play(FadeIn(title), run_time=0.6)
        self.next_slide()
        self.play(LaggedStart(*[FadeIn(VGroup(n, t), shift=UP * 0.1) for n, t in zip(nodes, texts)], lag_ratio=0.12), run_time=1.1)
        self.next_slide()
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.12), run_time=1.0)
        self.next_slide()
        self.play(Write(final), run_time=1.0)
        self.play(LaggedStart(*[pulse(VGroup(n, t), colors[i]) for i, (n, t) in enumerate(zip(nodes, texts))], lag_ratio=0.08), run_time=1.6)
        self.next_slide()
        self.wait(7.0)


class RCACopilotThirtySecondSummary(Scene):
    """A shorter recap scene for live demo insertion."""

    def construct(self) -> None:
        self.camera.background_color = DEEP_NAVY
        title = Text("OpenStack RCA Copilot", font=FONT, font_size=50, color=WHITE, weight=BOLD).to_edge(UP, buff=0.55)
        labels = ["Logs", "Parse", "Graph", "Bound", "Enrich", "Investigate", "Future AI"]
        colors = [GRAY, BLUE, PURPLE, RED, GREEN, CYAN, AMBER]
        nodes = VGroup(*[
            Circle(radius=0.38, color=c, fill_color=c, fill_opacity=0.18, stroke_width=4)
            for c in colors
        ]).arrange(RIGHT, buff=0.72).move_to(UP * 0.6)
        texts = VGroup(*[Text(l, font=FONT, font_size=21, color=WHITE).next_to(n, DOWN, buff=0.28) for l, n in zip(labels, nodes)])
        arrows = VGroup(*[make_arrow(nodes[i].get_right(), nodes[i + 1].get_left(), CYAN if i < 5 else AMBER, dashed=(i == 5)) for i in range(len(nodes) - 1)])
        caption = make_caption("Noisy logs become bounded, explainable investigation evidence.")
        caution = Text("correlation, not causality", font=FONT, font_size=25, color=PURPLE).next_to(nodes[2], UP, buff=0.45)
        self.play(FadeIn(title), run_time=0.7)
        self.play(LaggedStart(*[FadeIn(n, scale=0.8) for n in nodes], lag_ratio=0.08), FadeIn(texts), run_time=1.3)
        self.play(LaggedStart(*[Create(a) for a in arrows], lag_ratio=0.08), FadeIn(caution), run_time=1.2)
        self.play(FadeIn(caption), pulse(nodes[3], RED), pulse(nodes[4], GREEN), run_time=1.2)
        self.wait(1.0)
