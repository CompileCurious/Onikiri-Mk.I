# ⚠️ AI-Generated Content Notice

**This documentation and much of the project were created with significant assistance from AI tools (including GitHub Copilot powered by Anthropic Claude), as this is a solo developer project. Please review carefully.**

# H616 Kernel Patch Experiments

The build uses upstream Linux `v6.18.56`, then applies the pinned Armbian
`sunxi-6.18` DRM series at commit
`1f0b11116c21ec5781cfe271091fd189d3b869ba`. This supplies the H616 DE33 mixer,
TCON, and HDMI pipeline absent from the upstream SoC DTS.

The Pad 7 board DTS enables that pipeline and connects the HDMI output to the
internal panel connector. `build/build.sh` also applies the local
`003-dw-hdmi-force-connected-property.patch` for panels without usable HPD.
Other legacy patches in this directory are not applied.
