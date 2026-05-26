"""
Onikiri Mk.I — UI Theme
Centralised colour palette and style constants.

Aesthetic: black/red cyberpunk with old-Japan restraint.
No gradients, no rounded corners, no unnecessary motion.
"""

# ── Colours (RGBA floats, Kivy convention) ─────────────────────────────────────

BG_COLOR        = (0.039, 0.039, 0.039, 1.0)   # #0A0A0A  — display background
PANEL_BG        = (0.071, 0.071, 0.071, 1.0)   # #121212  — panel fill
PANEL_BG_ACTIVE = (0.090, 0.012, 0.012, 1.0)   # #170303  — panel when active
BORDER_COLOR    = (0.600, 0.000, 0.000, 1.0)   # #990000  — normal border
BORDER_ACTIVE   = (1.000, 0.000, 0.000, 1.0)   # #FF0000  — active border
BORDER_ERROR    = (1.000, 1.000, 1.000, 1.0)   # #FFFFFF  — error strobe frame A
BORDER_ERROR_B  = (1.000, 0.000, 0.000, 1.0)   # #FF0000  — error strobe frame B

TEXT_COLOR      = (0.900, 0.900, 0.900, 1.0)   # #E5E5E5  — primary text
TEXT_DIM        = (0.400, 0.400, 0.400, 1.0)   # #666666  — secondary / status text
TEXT_RED        = (1.000, 0.000, 0.000, 1.0)   # #FF0000  — alert text
TEXT_ACTIVE     = (1.000, 0.200, 0.200, 1.0)   # #FF3333  — active label

# Status strip colours
STATUS_IDLE     = (0.200, 0.200, 0.200, 1.0)   # #333333
STATUS_ACTIVE   = (0.600, 0.000, 0.000, 1.0)   # #990000
STATUS_RUNNING  = (1.000, 0.000, 0.000, 1.0)   # #FF0000
STATUS_ERROR    = (1.000, 1.000, 1.000, 1.0)   # #FFFFFF

# Flash colour for tap feedback
FLASH_COLOR     = (1.000, 0.000, 0.000, 0.35)

# ── Typography ─────────────────────────────────────────────────────────────────
# Use the system monospace font — no external font asset required.
FONT_MONO   = "RobotoMono"   # fallback to DroidSansMono if not present
FONT_SIZE_PANEL   = 22       # sp — panel label
FONT_SIZE_STATUS  = 11       # sp — status text
FONT_SIZE_OVERLAY = 16       # sp — overlay list items

# ── Layout ─────────────────────────────────────────────────────────────────────
BORDER_WIDTH  = 2            # dp — panel border
PANEL_PADDING = 10           # dp — internal panel padding
GRID_SPACING  = 4            # dp — spacing between panels
GRID_PADDING  = 6            # dp — outer grid padding
STATUS_HEIGHT = 14           # dp — status strip height at bottom of panel

# ── Animation timings ──────────────────────────────────────────────────────────
FLASH_DURATION   = 0.12      # seconds — tap flash
PULSE_INTERVAL   = 1.8       # seconds — active module pulse period
STROBE_INTERVAL  = 0.12      # seconds — error strobe toggle

# ── Panel registry ─────────────────────────────────────────────────────────────
# Maps UI label → supervisor module name
PANELS = [
    {"label": "RECON",      "module": "wifi_recon"},
    {"label": "MITM",       "module": "mitm"},
    {"label": "PAYLOADS",   "module": "payload_builder"},
    {"label": "WIRELESS",   "module": "bt_recon"},
    {"label": "ENGAGEMENT", "module": "engagement_loader"},
    {"label": "SYSTEM",     "module": "sysinfo"},
]

GRID_COLS = 3
GRID_ROWS = 2
