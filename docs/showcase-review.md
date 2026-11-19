# Showcase visual review

Reviewed November 18, 2026, using the same generated 83-row synthetic workshop
fixture before and after the changes. These are local browser captures, not proof
of public deployment. The after captures show the first comparison expanded.

| Viewport width | Before | After |
| --- | --- | --- |
| 390px mobile | [Before](review/showcase/before-mobile.png) | [After](review/showcase/after-mobile.png) |
| 1440px desktop | [Before](review/showcase/before-desktop.png) | [After](review/showcase/after-desktop.png) |

The demo now starts with three counts, a short finding and one suggested action.
Statistical methods and full numbers are available through **Statistical details**.
Charts have named controls, comparisons appear once, and the first three quality
findings are visible before **More findings**. Reliability cautions remain visible.

Browser checks passed at widths 320, 375, 390, 768 and 1440px, including expansion,
refresh and session recovery. The complete browser suite passed 28 tests. Captures
were visually inspected for readable labels, unclipped cards and mobile wrapping.
Physical phones, live HTTPS and printed QR codes still need release checks.

See [the change log](showcase-changes.md) for the PDF feedback resolutions and
[deployment instructions](deployment.md) for `spteamscience.com`.
