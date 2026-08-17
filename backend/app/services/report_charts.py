"""Deterministic chart rendering for the dashboard export -- matplotlib on
the headless Agg backend. Every figure here is drawn straight from numbers
already computed by the same overview/trend functions the live dashboard
calls; nothing here is AI-generated or approximated."""

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_CURRENT_COLOR = "#127a45"
_PRIOR_COLOR = "#eb6834"


def render_bar_chart(
    labels: list[str],
    current: list[float | None],
    prior: list[float | None] | None,
    title: str,
    unit: str,
) -> bytes:
    """A small current-vs-prior-year bar chart as PNG bytes, matching the
    dashboard's own green/orange convention. `prior` may be None (or all
    None) if no year-over-year data applies -- current-only bars then."""
    has_prior = prior is not None and any(v is not None for v in prior)

    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=150)
    x = range(len(labels))
    width = 0.36 if has_prior else 0.55
    cur_vals = [v if v is not None else 0 for v in current]
    cur_x = [i - width / 2 for i in x] if has_prior else list(x)
    ax.bar(cur_x, cur_vals, width=width, color=_CURRENT_COLOR, label="This period")
    if has_prior:
        prior_vals = [v if v is not None else 0 for v in prior]  # type: ignore[union-attr]
        prior_x = [i + width / 2 for i in x]
        ax.bar(prior_x, prior_vals, width=width, color=_PRIOR_COLOR, label="Same period last year")

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_title(title, fontsize=10, loc="left", fontweight="bold", color="#101828")
    ax.set_ylabel(unit, fontsize=8, color="#667085")
    ax.tick_params(colors="#667085", labelsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#d0d5dd")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#eaecf0", linewidth=0.7)
    if has_prior:
        ax.legend(fontsize=7, frameon=False, loc="upper right")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
