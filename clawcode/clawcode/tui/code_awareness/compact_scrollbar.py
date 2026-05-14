"""Scrollbar rendering for Code Awareness: compact vertical thumb like a short block.

Textual draws the thumb length as (window_size / virtual_size) * track_height. When only a
few lines overflow the panel, that ratio is large and the thumb becomes a tall strip. The
main chat MessageList usually has much more scrollable content, so its thumb looks like a
small block. We cap the vertical thumb height so the code tree panel matches that look
while keeping scroll position math unchanged (only the thumb length is clamped).
"""

from __future__ import annotations

from math import ceil

from rich.color import Color
from rich.segment import Segment, Segments
from rich.style import Style

from textual.scrollbar import ScrollBarRender


class CompactVerticalThumbScrollBarRender(ScrollBarRender):
    """Same as Textual's bar renderer, but vertical thumb height has a small upper bound."""

    MAX_THUMB_ROWS: int = 5

    @classmethod
    def render_bar(
        cls,
        size: int = 25,
        virtual_size: float = 50,
        window_size: float = 20,
        position: float = 0,
        thickness: int = 1,
        vertical: bool = True,
        back_color: Color = Color.parse("#555555"),
        bar_color: Color = Color.parse("bright_magenta"),
    ) -> Segments:
        if vertical:
            bars = cls.VERTICAL_BARS
        else:
            bars = cls.HORIZONTAL_BARS

        back = back_color
        bar = bar_color

        len_bars = len(bars)

        width_thickness = thickness if vertical else 1

        _Segment = Segment
        _Style = Style
        blank = cls.BLANK_GLYPH * width_thickness

        foreground_meta = {"@mouse.down": "grab"}
        if window_size and size and virtual_size and size != virtual_size:
            bar_ratio = virtual_size / size
            thumb_size = max(1, window_size / bar_ratio)
            if vertical:
                thumb_size = min(thumb_size, float(cls.MAX_THUMB_ROWS))
                thumb_size = min(thumb_size, float(max(1, size)))

            position_ratio = position / (virtual_size - window_size)
            position = (size - thumb_size) * position_ratio

            start = int(position * len_bars)
            end = start + ceil(thumb_size * len_bars)

            start_index, start_bar = divmod(max(0, start), len_bars)
            end_index, end_bar = divmod(max(0, end), len_bars)

            upper = {"@mouse.down": "scroll_up"}
            lower = {"@mouse.down": "scroll_down"}

            upper_back_segment = Segment(blank, _Style(bgcolor=back, meta=upper))
            lower_back_segment = Segment(blank, _Style(bgcolor=back, meta=lower))

            segments = [upper_back_segment] * int(size)
            segments[end_index:] = [lower_back_segment] * (size - end_index)

            segments[start_index:end_index] = [
                _Segment(blank, _Style(color=bar, reverse=True, meta=foreground_meta))
            ] * (end_index - start_index)

            if start_index < len(segments):
                bar_character = bars[len_bars - 1 - start_bar]
                if bar_character != " ":
                    segments[start_index] = _Segment(
                        bar_character * width_thickness,
                        (
                            _Style(bgcolor=back, color=bar, meta=foreground_meta)
                            if vertical
                            else _Style(
                                bgcolor=back,
                                color=bar,
                                meta=foreground_meta,
                                reverse=True,
                            )
                        ),
                    )
            if end_index < len(segments):
                bar_character = bars[len_bars - 1 - end_bar]
                if bar_character != " ":
                    segments[end_index] = _Segment(
                        bar_character * width_thickness,
                        (
                            _Style(
                                bgcolor=back,
                                color=bar,
                                meta=foreground_meta,
                                reverse=True,
                            )
                            if vertical
                            else _Style(bgcolor=back, color=bar, meta=foreground_meta)
                        ),
                    )
        else:
            style = _Style(bgcolor=back)
            segments = [_Segment(blank, style=style)] * int(size)
        if vertical:
            return Segments(segments, new_lines=True)
        return Segments((segments + [_Segment.line()]) * thickness, new_lines=False)


__all__ = ["CompactVerticalThumbScrollBarRender"]
