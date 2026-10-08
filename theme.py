"""Visual language: palette, typography, spacing scale.

Design rules:
  - One accent color. Everything else in neutral greys.
  - Space instead of borders. Dividers are 1 px and very low contrast.
  - Do not step outside the four-step type scale.
"""

PALETTES = {
    "dark": {
        "bg":          "#0F1115",
        "surface":     "#151821",
        "surface_2":   "#1B1F2A",
        "surface_3":   "#222733",
        "border":      "#242935",
        "text":        "#E7E9EE",
        "text_dim":    "#8B92A0",
        "text_faint":  "#5D6472",
        "accent":      "#5B8DEF",
        "accent_soft": "#2B3A57",
        "positive":    "#4CAF7D",
        "negative":    "#E0715F",
        "series": ["#5B8DEF", "#7C6FF0", "#4FB3A5", "#D9A05B", "#CE7A6D", "#454B59"],
    },
    "light": {
        "bg":          "#FAFAFB",
        "surface":     "#FFFFFF",
        "surface_2":   "#F3F4F7",
        "surface_3":   "#E9EBF0",
        "border":      "#E4E6EC",
        "text":        "#14161C",
        "text_dim":    "#666D7A",
        "text_faint":  "#9AA0AC",
        "accent":      "#3B6FD4",
        "accent_soft": "#D4E0F7",
        "positive":    "#2E8B5F",
        "negative":    "#C2503F",
        "series": ["#3B6FD4", "#6455C8", "#358A7D", "#B8823C", "#B05B4C", "#C3C7D0"],
    },
}

FAMILY = "Segoe UI"

# Four-step scale: body, label, heading, figure
SIZE = {
    "caption": 8,
    "small":   9,
    "body":    10,
    "label":   11,
    "title":   13,
    "stat":    19,
    "display": 22,
}

SPACE = {"xs": 4, "sm": 8, "md": 14, "lg": 22, "xl": 32}


def font(size="body", weight="normal"):
    return (FAMILY, SIZE.get(size, size) if isinstance(size, str) else size, weight)


def _to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def mix(color_a, color_b, ratio):
    """Blend between color_a and color_b. ratio=0 -> a, ratio=1 -> b."""
    ratio = max(0.0, min(1.0, ratio))
    a, b = _to_rgb(color_a), _to_rgb(color_b)
    blended = tuple(round(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
    return "#%02X%02X%02X" % blended


def palette(name):
    return PALETTES.get(name, PALETTES["dark"])
