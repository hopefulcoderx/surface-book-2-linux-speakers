#!/usr/bin/env bash
# Install the Surface Book 2 Dolby speaker preset for EasyEffects 8 (Flatpak or native).
set -euo pipefail
cd "$(dirname "$0")"

APP=com.github.wwmm.easyeffects
if flatpak info "$APP" >/dev/null 2>&1; then
    DATA="$HOME/.var/app/$APP/data/easyeffects"
    CONF="$HOME/.var/app/$APP/config/easyeffects/db/easyeffectsrc"
    EXEC="flatpak run $APP"
elif command -v easyeffects >/dev/null; then
    DATA="${XDG_DATA_HOME:-$HOME/.local/share}/easyeffects"
    CONF="${XDG_CONFIG_HOME:-$HOME/.config}/easyeffects/db/easyeffectsrc"
    EXEC="easyeffects"
else
    echo "EasyEffects not found. Install it first:"
    echo "  flatpak install flathub $APP"
    exit 1
fi

mkdir -p "$DATA/output" "$DATA/autoload/output"
cp "presets/Surface Book 2 Dolby.json" "presets/Headphones (flat).json" "$DATA/output/"
echo "Presets installed to $DATA/output"

# Autoload: Dolby on the built-in speakers, flat on everything else (headphone jack, Bluetooth,
# USB, HDMI). Windows also turns the Dolby speaker tuning off for other outputs.
SINK=$(pactl list short sinks | awk '$2 ~ /^alsa_output\.pci-.*analog-stereo/ {print $2; exit}')
if [[ -n $SINK ]]; then
    DESC=$(pactl list sinks | awk -v s="$SINK" '$1=="Name:" {f=($2==s)} f && $1=="Description:" {sub(/^[ \t]*Description: /,""); print; exit}')
    cat > "$DATA/autoload/output/$SINK:Speakers.json" <<JSON
{
    "device": "$SINK",
    "device-description": "$DESC",
    "device-profile": "Speakers",
    "preset-name": "Surface Book 2 Dolby"
}
JSON
    echo "Autoload: speakers -> Surface Book 2 Dolby"
else
    echo "Built-in speakers not found; set the autoload rule in EasyEffects -> Presets -> Autoload."
fi

# Fallback preset for every other output. EasyEffects rewrites its config on exit, so quit it first.
$EXEC --quit >/dev/null 2>&1 || true
sleep 2
mkdir -p "$(dirname "$CONF")"
touch "$CONF"
sed -i '/^outputAutoloadingFallbackPreset=/d; /^outputAutoloadingUsesFallback=/d' "$CONF"
grep -q '^\[Window\]' "$CONF" || printf '\n[Window]\n' >> "$CONF"
sed -i 's/^\[Window\]$/[Window]\noutputAutoloadingFallbackPreset=Headphones (flat)\noutputAutoloadingUsesFallback=true/' "$CONF"
echo "Autoload fallback: all other outputs -> Headphones (flat)"

read -rp "Start EasyEffects in the background at login? [y/N] " ans
if [[ $ans =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/autostart"
    sed "s|^Exec=.*|Exec=sh -c \"sleep 8; $EXEC --service-mode --hide-window\"|" \
        autostart/easyeffects-service.desktop > "$HOME/.config/autostart/easyeffects-service.desktop"
    echo "Autostart entry added."
fi

echo "Done. Start EasyEffects; the preset switches automatically with the output device."
