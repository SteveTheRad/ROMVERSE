from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap

_SHAPES = {
    "device": '<rect x="8" y="7" width="16" height="18" rx="3"/><circle cx="16" cy="21" r="1"/>',
    "diagnostics": '<path d="M6 17h4l2-7 3 11 2-6h5"/>',
    "history": '<path d="M8 9a9 9 0 1 1-1 9"/><path d="M8 5v5H3"/><path d="M16 11v5l3 2"/>',
    "guardian": '<path d="M16 4l8 3v6c0 5-3 9-8 12-5-3-8-7-8-12V7l8-3z"/><path d="M12 15l2 2 5-5"/>',
    "repair": '<path d="M20 6a5 5 0 0 0-6 6L6 20l2 2 8-8a5 5 0 0 0 6-6l-3 3-3-3 4-2z"/>',
    "packs": '<path d="M5 9l11-5 6 3-11 5z"/><path d="M5 9v9l6 3v-9zM22 7v9l-11 5"/>',
    "rom": '<path d="M7 4h11l3 3v14H7z"/><path d="M10 12h8M10 16h6"/>',
    "apk": '<rect x="7" y="8" width="18" height="14" rx="3"/><path d="M10 8l-2-3m7 3V3m5 5 2-3M11 14h.01M20 14h.01M11 18h9"/>',
    "backup": '<path d="M7 20a5 5 0 0 1 1-10 8 8 0 0 1 15 3 4 4 0 0 1-1 7H7z"/><path d="M16 13v7m-3-3 3 3 3-3"/>',
    "galaxy": '<circle cx="16" cy="16" r="3"/><path d="M4 16c3-8 21-8 24 0-3 8-21 8-24 0z"/><path d="M16 4c8 3 8 21 0 24-8-3-8-21 0-24z"/>',
}

_QUICK_ACTION_SHAPES = {
    "rocket": (
        '<path d="M4.5 16.5c-1.5 1.3-2 5-2 5s3.7-.5 5-2c.7-.8.7-2.1-.1-2.9s-2.1-.8-2.9-.1z"/>'
        '<path d="m12 15-3-3c.7-1.7 1.3-2.9 2-4 2.1-3.1 5.7-5.4 11-6-0.6 5.3-2.9 8.9-6 11-1.1.7-2.3 1.3-4 2z"/>'
        '<path d="M9 12H4s.6-3.1 2-4c1.6-1.1 5 0 5 0M12 15v5s3.1-.6 4-2c1.1-1.6 0-5 0-5"/>'
        '<circle cx="16" cy="8" r="1"/>'
    ),
    "terminal": ('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="m7 8 3 3-3 3m5 2h5"/>'),
    "trash": ('<path d="M3 6h18M8 6V4h8v2m3 0-1 15H6L5 6m4 4v7m6-7v7"/>'),
    "sliders": (
        '<path d="M21 4h-7M10 4H3m18 8h-9m-4 0H3m18 8h-5m-4 0H3"/>'
        '<circle cx="12" cy="4" r="2"/><circle cx="10" cy="12" r="2"/>'
        '<circle cx="14" cy="20" r="2"/>'
    ),
    "puzzle": (
        '<path d="M4 6h5V4a3 3 0 1 1 6 0v2h5v5h2a3 3 0 1 1 0 6h-2v5h-5v-2a3 3 0 1 0-6 0v2H4v-5h2a3 3 0 1 0 0-6H4z"/>'
    ),
    "cloud_upload": (
        '<path d="M12 21V13m-4 4 4-4 4 4"/>'
        '<path d="M5 17H4a4 4 0 0 1-.4-8A7 7 0 0 1 17 7a5 5 0 0 1 3 9.9"/>'
    ),
    "restore": ('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'),
}

_SIDEBAR_SHAPES = {
    "dashboard": (
        '<rect x="3" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1.5"/>'
    ),
    "build": _QUICK_ACTION_SHAPES["rocket"],
    "optimizer": _QUICK_ACTION_SHAPES["sliders"],
    "mods": _QUICK_ACTION_SHAPES["puzzle"],
    "repair": (
        '<path d="M14.5 6.5a5 5 0 0 0-6.2 6.2L3 18l3 3 5.3-5.3a5 5 0 0 0 6.2-6.2l-3.2 3.2-3-3z"/>'
        '<path d="m14 17 4 4 3-3-4-4"/>'
    ),
    "guardian": (
        '<path d="M12 2.5 20 6v5.8c0 4.7-2.7 7.8-8 10.2-5.3-2.4-8-5.5-8-10.2V6z"/>'
        '<path d="m8.5 12 2.2 2.2 4.8-5"/>'
    ),
    "apk": (
        '<rect x="4" y="7" width="16" height="14" rx="3"/>'
        '<path d="m7 7-2-3m12 3 2-3M8 13h.01M16 13h.01M8 17h8"/>'
    ),
    "backup": _QUICK_ACTION_SHAPES["cloud_upload"],
    "logs": ('<path d="M5 3h10l4 4v14H5z"/><path d="M15 3v5h4"/><path d="M8 11h8M8 15h8M8 19h5"/>'),
    "knowledge": (
        '<path d="M3 5.5c3.4-1 6.4-.5 9 1.5v14c-2.6-2-5.6-2.5-9-1.5z"/>'
        '<path d="M21 5.5c-3.4-1-6.4-.5-9 1.5v14c2.6-2 5.6-2.5 9-1.5z"/>'
    ),
    "terminal": _QUICK_ACTION_SHAPES["terminal"],
    "toolchain": (
        '<path d="m4 4 16 16M6 3l3 1-5 5-1-3zM18 21l3-3"/>'
        '<path d="M15 5a4 4 0 0 0-4.5 5.5L3 18l3 3 7.5-7.5A4 4 0 0 0 19 9l-2.5 2.5-3-3z"/>'
    ),
    "companion": (
        '<rect x="6" y="2.5" width="12" height="19" rx="3"/>'
        '<path d="M10 18.5h4M9 8a4.5 4.5 0 0 1 6 0M11 10.5a2 2 0 0 1 2 0"/>'
    ),
    "members": (
        '<circle cx="12" cy="8" r="3.5"/>'
        '<path d="M5 21c.7-5 3-7.5 7-7.5s6.3 2.5 7 7.5"/>'
        '<path d="m17.5 7.5 1.2 1.2 2.3-2.5"/>'
    ),
    "galaxy": (
        '<circle cx="12" cy="12" r="2.5"/>'
        '<ellipse cx="12" cy="12" rx="10" ry="4.5"/>'
        '<path d="M7 3.5c5.2 2.4 8.7 8.8 9.5 17"/>'
        '<circle cx="21" cy="12" r="1" fill="url(#q)" stroke="none"/>'
    ),
    "about": (
        '<circle cx="12" cy="12" r="9.5"/><path d="M12 10.5V17"/>'
        '<circle cx="12" cy="7" r=".8" fill="url(#q)" stroke="none"/>'
    ),
}


def cosmic_icon(name: str, size: int = 22) -> QIcon:
    shape = _SHAPES.get(name, _SHAPES["galaxy"])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="#C86BFF"/><stop offset=".55" stop-color="#5E83FF"/><stop offset="1" stop-color="#28E7F5"/>
      </linearGradient></defs>
      <circle cx="16" cy="16" r="13" fill="#101735" stroke="#314B9A"/>
      <g fill="none" stroke="url(#g)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{shape}</g>
      <circle cx="7" cy="7" r="1" fill="#76F6FF"/><circle cx="25" cy="25" r="1" fill="#D990FF"/>
    </svg>"""
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    return QIcon(pixmap.scaled(size, size))


def quick_action_icon(
    name: str,
    size: int = 44,
    start: str = "#A84EFF",
    end: str = "#5E83FF",
) -> QIcon:
    """Reference-style standalone neon icon with no enclosing badge."""
    shape = _QUICK_ACTION_SHAPES.get(name, _QUICK_ACTION_SHAPES["sliders"])
    render_size = size * 4
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{render_size}" height="{render_size}" viewBox="0 0 48 48" shape-rendering="geometricPrecision">
      <defs><linearGradient id="q" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/>
      </linearGradient></defs>
      <g transform="scale(2)" fill="none" stroke="url(#q)" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{shape}</g>
    </svg>"""
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    pixmap.setDevicePixelRatio(4.0)
    return QIcon(pixmap)


def sidebar_icon(
    name: str,
    size: int = 26,
    start: str = "#A84EFF",
    end: str = "#28DDF4",
    *,
    active: bool = False,
) -> QIcon:
    """Crisp standalone neon icon matching the dashboard Quick Actions."""
    shape = _SIDEBAR_SHAPES.get(name, _SIDEBAR_SHAPES["about"])
    render_size = size * 4
    glow = ""
    stroke_width = "1.85" if active else "1.6"
    if active:
        glow = (
            f'<g transform="scale(2)" fill="none" stroke="{start}" opacity=".20" '
            f'stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round">{shape}</g>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{render_size}" height="{render_size}" viewBox="0 0 48 48" shape-rendering="geometricPrecision">
      <defs><linearGradient id="q" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/>
      </linearGradient></defs>
      {glow}
      <g transform="scale(2)" fill="none" stroke="url(#q)" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round">{shape}</g>
    </svg>"""
    pixmap = QPixmap()
    pixmap.loadFromData(svg.encode("utf-8"), "SVG")
    pixmap.setDevicePixelRatio(4.0)
    return QIcon(pixmap)
