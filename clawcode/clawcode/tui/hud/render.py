from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .state import HudState, HudAgentEntry, HudRunningTool, HudTodoItem
from .tool_display import hud_tool_display_name

_AGENT_TOOL_NAMES = frozenset({"agent", "Agent", "Task"})


@dataclass(frozen=True)
class HudColors:
    """Customizable Rich markup colors for HUD rows."""
    model: str = "cyan"
    tool_running: str = "yellow"
    tool_name: str = "cyan"
    tool_done: str = "green"
    agent_type: str = "magenta"
    todo_bullet: str = "yellow"


_DEFAULT_HUD_COLORS = HudColors()


def _truncate(text: str, max_len: int) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _escape_rich_markup(text: str) -> str:
    return (text or "").replace("[", "\\[").replace("]", "\\]")


def _strip_rich_tags(text: str) -> str:
    """Remove Rich markup tags for width calculation.
    
    Handles various Rich tag formats:
    - [color]text[/] - color tags
    - [bold]text[/bold] - style tags  
    - [dim]text[/] - dim/bright tags
    - \\[escaped\\] - escaped brackets (keep the inner content)
    """
    import re
    # First, handle escaped brackets: convert \\[text\\] to [text] (keep content)
    text = re.sub(r'\\\[', '[', text)
    text = re.sub(r'\\\]', ']', text)
    # Remove closing tags [/tag]
    text = re.sub(r'\[/[^\]]*\]', '', text)
    # Remove opening tags [tag] (including color, style, dim, etc.)
    text = re.sub(r'\[[^\]]*\]', '', text)
    return text


def _display_width(text: str) -> int:
    """Calculate display width accounting for CJK and special chars."""
    width = 0
    for char in _strip_rich_tags(text):
        # CJK characters typically take 2 columns in terminals
        if '\u4e00' <= char <= '\u9fff' or '\u3000' <= char <= '\u303f':
            width += 2
        # Box drawing and block characters
        elif '\u2500' <= char <= '\u257f' or '\u2580' <= char <= '\u259f':
            width += 1
        # Emoji and symbols
        elif ord(char) > 0x1f300:
            width += 2
        else:
            width += 1
    return width


def _context_color_tag(percent: int) -> str:
    if percent >= 85:
        return "red"
    if percent >= 70:
        return "yellow"
    return "green"


def render_context_bar(percent: int) -> str:
    percent = max(0, min(100, int(percent or 0)))
    filled = int(round(percent / 10.0))
    filled = max(0, min(10, filled))
    empty = 10 - filled
    color = _context_color_tag(percent)
    # Use standard ASCII characters for consistent terminal width
    # Block characters like '█' (U+2588) can have inconsistent widths in some terminals
    # Using '=' for filled and '-' for empty provides consistent 1-column width
    return f"[{color}]{'=' * filled}[/][dim]{'-' * empty}[/]"


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return "<1m"
    total_mins = int(seconds // 60)
    if total_mins < 60:
        return f"{total_mins}m"
    hours = total_mins // 60
    rem_mins = total_mins % 60
    return f"{hours}h {rem_mins}m"


def format_hud_session_duration(seconds: float) -> str:
    """Session-line timer label (<1m / Nm / Nh Mm)."""
    return _format_duration(max(0.0, seconds))


def _format_elapsed(seconds: float) -> str:
    if seconds < 1:
        return "<1s"
    if seconds < 60:
        return f"{int(round(seconds))}s"
    mins = int(seconds // 60)
    secs = int(round(seconds % 60))
    return f"{mins}m {secs}s"


# ---------------------------------------------------------------------------
# Row renderers (return None when there's no content for the row)
# ---------------------------------------------------------------------------


def _render_session_line(state: HudState, colors: HudColors, max_width: int = 120) -> str:
    """Render session line with intelligent truncation to fit within max_width.
    
    Priority order (high to low):
    1. Model name (essential)
    2. Context bar + percent (essential)
    3. clawcode.md count
    4. rules count
    5. MCPs count
    6. hooks count
    7. Duration
    8. Project hint (most likely to be truncated)
    """
    model = _escape_rich_markup(state.model or "Unknown")
    percent = max(0, min(100, state.context_percent))

    color = _context_color_tag(percent)
    bar = render_context_bar(percent)
    percent_tag = f"[{color}]{percent}%[/]"

    cc = state.config_counts
    duration = state.session_duration.strip()
    hint = (state.project_hint or "").strip()
    
    # Build line progressively, checking width at each step
    parts: List[str] = [
        f"[{colors.model}]\\[{model}][/]",
        bar,
        percent_tag,
    ]
    
    # Helper to calculate actual display width by stripping Rich tags
    def display_width(parts_list: List[str]) -> int:
        # Join with separator and strip Rich tags to get actual display width
        joined = " | ".join(parts_list)
        plain = _strip_rich_tags(joined)
        return len(plain)
    
    # Add optional parts if they fit
    optional_parts = [
        f"[dim]{cc.claude_md_count} clawcode.md[/]",
        f"[dim]{cc.rules_count} rules[/]",
        f"[dim]{cc.mcp_count} MCPs[/]",
        f"[dim]{cc.hooks_count} hooks[/]",
    ]
    
    for part in optional_parts:
        test_parts = parts + [part]
        if display_width(test_parts) <= max_width:
            parts.append(part)
    
    # Try to add duration if it fits
    if duration:
        duration_part = f"[dim]{duration}[/]"
        test_parts = parts + [duration_part]
        if display_width(test_parts) <= max_width:
            parts.append(duration_part)
    
    # Add hint with truncation - this is lowest priority and most likely to be shortened
    if hint:
        # Calculate remaining space
        current_width = display_width(parts)
        separator_width = 3 if parts else 0
        remaining = max_width - current_width - separator_width
        
        if remaining > 10:  # Only add if we have reasonable space
            # Truncate hint to fit
            max_hint_len = max(10, remaining - 5)  # Leave some margin
            if len(hint) > max_hint_len:
                hint = hint[:max_hint_len-3] + "..."
            parts.append(f"[dim]{_escape_rich_markup(hint)}[/]")
    
    return " | ".join(parts)


def _render_tools_line(
    tool_counts: Dict[str, int], running_tools: List[HudRunningTool], colors: HudColors,
) -> str | None:
    parts: List[str] = []

    for rt in running_tools[-2:]:
        nm = _escape_rich_markup(hud_tool_display_name(rt.name))
        tgt = (rt.target or "").strip()
        if tgt:
            tgt_esc = _escape_rich_markup(tgt)
            parts.append(f"[{colors.tool_running}]◐[/] [{colors.tool_name}]{nm}[/][dim]: {tgt_esc}[/]")
        else:
            parts.append(f"[{colors.tool_running}]◐[/] [{colors.tool_name}]{nm}[/]")

    completed_items = sorted(
        ((n, c) for n, c in tool_counts.items() if c > 0 and n not in _AGENT_TOOL_NAMES),
        key=lambda kv: (-kv[1], kv[0]),
    )[:4]
    for name, count in completed_items:
        label = hud_tool_display_name(name)
        parts.append(f"[{colors.tool_done}]✓[/] {_escape_rich_markup(label)} [dim]×{count}[/]")

    if not parts:
        return None
    return " | ".join(parts)


def _render_agent_entry(agent: HudAgentEntry, *, now: float, colors: HudColors) -> str:
    status_color = colors.tool_running if agent.status == "running" else colors.tool_done
    icon = "◐" if agent.status == "running" else "✓"

    desc_raw = _truncate(agent.description, 40)
    desc = _escape_rich_markup(desc_raw)
    elapsed_seconds = ((agent.end_time or now) - agent.start_time) if agent.start_time else 0.0
    elapsed = _format_elapsed(max(0.0, elapsed_seconds))

    type_raw = (agent.subagent_type or "").strip().rstrip(":").strip()
    subagent_type = _escape_rich_markup(type_raw)
    model = (agent.model or "").strip()
    model_part = f" [dim]\\[{_escape_rich_markup(model)}][/]" if model else ""
    desc_suffix = f": {desc}" if desc else ""
    return (
        f"[{status_color}]{icon}[/] [{colors.agent_type}]{subagent_type}[/]{model_part}{desc_suffix} "
        f"[dim]({elapsed})[/]"
    )


def _render_agents_line(agent_entries: List[HudAgentEntry], *, now: float, colors: HudColors) -> str | None:
    if not agent_entries:
        return None
    running = [a for a in agent_entries if a.status == "running"]
    completed_recent = [a for a in agent_entries if a.status != "running"][-2:]
    to_show = (running + completed_recent)[-3:]
    if not to_show:
        return None
    return "\n".join(_render_agent_entry(a, now=now, colors=colors) for a in to_show)


def _render_todos_line(todos: List[HudTodoItem], colors: HudColors) -> str | None:
    if not todos:
        return None
    in_progress = next((t for t in todos if t.status == "in_progress"), None)
    completed = sum(1 for t in todos if t.status == "completed")
    total = len(todos)
    if in_progress is None:
        if total > 0 and completed == total:
            return f"[{colors.tool_done}]✓[/] All todos complete [dim]({completed}/{total})[/]"
        return None
    content = _escape_rich_markup(_truncate(in_progress.content, 50))
    return f"[{colors.todo_bullet}]▸[/] {content} [dim]({completed}/{total})[/]"


def _render_deep_loop_line(deep_loop_status: str, colors: HudColors) -> str:
    """Render an active deep_loop status row with Rich markup.

    The raw *deep_loop_status* string is built in ChatScreen._update_status_bars
    and already contains the key information (iter, max, idle, stall).  Here we
    apply colours so it stands out from the surrounding HUD rows.

    Example outputs:
        ◐ [深度循环] 迭代 3/10 | 运行中
        ○ [深度循环] 迭代 3/10 | 等待 12s
        ⟳ [深度循环] 迭代 4/10 | 自动恢复×1 | 等待 5s
    """
    if not deep_loop_status:
        return ""
    escaped = _escape_rich_markup(deep_loop_status)
    # Highlight the status line using the agent_type color so it is visually distinct.
    return f"[{colors.agent_type}]{escaped}[/]"


def _clamp_line(line: str, max_width: int = 200) -> str:
    """Clamp line to maximum display width, truncating with '...' if needed.
    
    Accounts for Rich markup tags which don't contribute to display width.
    """
    if not line:
        return ""
    
    # Simple heuristic: if raw line length (including tags) is under limit, return as-is
    if len(line) <= max_width:
        return line
    
    # For longer lines, we need to truncate carefully preserving Rich tags
    # A conservative approach: truncate the raw string and hope for the best
    # The display width will be less than the raw length due to tags
    return line[:max_width - 3] + "..."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_hud(state: HudState, *, now: float = 0.0, colors: HudColors | None = None) -> str:
    """Render 5 content lines + 1 trailing blank row (6 lines total; stable height).

    Row layout (matches claude-hud red-box screenshot):
        1  session: model | bar | % | CLAUDE.md | rules | MCPs | hooks | path | timer
        2  tools:   running ◐ + completed ✓ counts
        3  agent slot 1
        4  agent slot 2
        5  todos summary
        6  (empty spacer — avoids last-line glyph clipping with CJK / some terminals)
    Empty rows are blank (dark background, no placeholder characters).
    """
    c = colors or _DEFAULT_HUD_COLORS
    # Session line with width constraint to prevent overflow (typical terminal width ~100-120)
    lines: List[str] = [_render_session_line(state, c, max_width=100)]

    tools = _render_tools_line(state.tool_counts, state.running_tools, c)
    lines.append(tools or "")

    agents_block = _render_agents_line(state.agent_entries, now=now, colors=c)
    if agents_block:
        agent_lines = [ln for ln in agents_block.split("\n") if ln.strip()][-2:]
    else:
        agent_lines = []
    while len(agent_lines) < 2:
        agent_lines.append("")
    lines.extend(agent_lines)

    # Row 5: deep_loop status takes priority over todos when a loop is active.
    if state.deep_loop_status:
        lines.append(_render_deep_loop_line(state.deep_loop_status, c))
    else:
        todos = _render_todos_line(state.todos, c)
        lines.append(todos or "")

    while len(lines) < 5:
        lines.append("")

    lines = lines[:5]
    # Final safety clamp to prevent any overflow causing border misalignment
    lines = [_clamp_line(ln, max_width=200) for ln in lines]
    lines.append("")
    return "\n".join(lines)
