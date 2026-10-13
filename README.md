# Surface Book 2 Linux Speakers

Windows-like speaker sound for the **Microsoft Surface Book 2** on Linux, using the
**original Dolby speaker tuning** Microsoft ships in its Windows driver, converted into an
[EasyEffects](https://github.com/wwmm/easyeffects) preset.

On Linux the speakers play with no correction, so they sound thin and boxy. On Windows,
Dolby applies a per-speaker correction curve. This repo extracts that curve and recreates it.

## Quick start

```bash
flatpak install flathub com.github.wwmm.easyeffects
git clone https://github.com/USER/surface-book-2-linux-speakers.git
cd surface-book-2-linux-speakers
./install.sh
```

Then open **Easy Effects → Presets → Surface Book 2 Dolby**.

`install.sh` also sets up autoloading: the Dolby preset on the built-in speakers, and a flat
preset (no effects) as the fallback for every other output: headphone jack, Bluetooth headphones
and speakers, USB, HDMI. On Windows the Dolby speaker tuning is also off for other outputs.
You can see or change this in **Easy Effects → Presets → Autoload**.

## What the preset does

The Dolby "audio optimizer" curve from the driver, applied separately to the left and right speakers:

| Range | Left | Right | Effect |
|---|---|---|---|
| 47 Hz | −13 dB | −16 dB | Cuts deep bass the speakers can't reproduce |
| 140–330 Hz | +9 to +11 dB | +10 to +12 dB | Fuller body |
| 650 Hz–1 kHz | −2.5 to −4 dB | −1 to −2 dB | Less boxy |
| 2–11 kHz | +2 to +5 dB | +1 to +4 dB | Clarity |

Then Dolby's **audio regulator** (speaker protection), approximated with a multiband compressor.
It stops the small speakers distorting at high volume. The strictest band is 280–1500 Hz, the vocal range:

| Band | Limits above | Dolby value |
|---|---|---|
| < 100 Hz | −40 dB | −60 dB |
| 100–280 Hz | −10 dB | −9 to −11 dB |
| 280–1500 Hz | −17 dB | −15 to −21 dB |
| 1.5–2 kHz | −10 dB | −10 dB |
| > 2 kHz | — | not regulated |

Then Dolby's **intelligent EQ** (parameter 13) target curve, as a static EQ scaled to the IEQ amount
(10/16) and centred on 0 dB: about +4 dB at 2–4.5 kHz for clearer voices, rolling off above 10 kHz.
On Windows the IEQ is dynamic, so this is an approximation.

Chain: 20-band split-channel equalizer → 20-band IEQ equalizer → multiband compressor (ratio 4:1, 5 ms attack, 120 ms release) → limiter at −1 dB.

## Where the tuning comes from

The official driver package
(`SurfaceBook2_Win11_22000_23.092.25731.0.msi`, from the
[Microsoft Download Center](https://www.microsoft.com/en-us/download/details.aspx?id=56261))
contains the Realtek audio INF. For the Surface Book 2 codec (Realtek ALC298, subsystem
`10EC1146`) it defines a Dolby DAX2 preset `DAX2Preset1146_SPK` as registry values:

- Dolby DAP v2 parameters stored as `PROPVARIANT`s (int or int array), gains in **1/16 dB**
- **Parameter 18 = audio optimizer**: 20 band frequencies + per-channel gains (all zero for headphones)
- **Parameter 22 = audio regulator**: per-band high/low thresholds + isolated-band flags (headphones: flat −12/0 dB).
  The "low" thresholds are used as dBFS limits. This reading is an interpretation tuned by ear: the curve (param 18) is exact, the regulator is an approximation

The Dolby processing itself runs as Intel SST DSP firmware (`lib_dolby.bin`), so the newer
[DAX3 XML converter](https://github.com/antoinecellerier/speaker-tuning-to-easyeffects)
does not apply to this model.

### Regenerate it yourself

```bash
sudo apt install 7zip
python3 scripts/extract_dolby_tuning.py
```

It downloads the driver package (~1.9 GB, to a temp dir that is deleted afterwards), detects
your codec subsystem id, decodes the preset and writes `Surface Book 2 Dolby.json`.
Use `--subsys XXXX` if your model reports a different id.

## Tested on

- Surface Book 2 13" with dGPU, Pop!_OS 24.04 (COSMIC), linux-surface kernel 6.19, PipeWire 1.6, EasyEffects 8.3 (Flatpak)

## Notes

- **Autostart on COSMIC:** the in-app "start at login" toggle doesn't work (no Background portal), so
  `install.sh` adds an XDG autostart entry instead.
- **Regulator is approximate:** on Windows it reacts to the system volume; here it reacts to the music's level
  (the volume slider acts after EasyEffects). Tested clean at 100% volume.
- **Not reproduced:** Dolby's adaptive Intelligent Equalizer (parameter 13).
- No Microsoft or Dolby files are redistributed here. Only the derived EQ values are included.

## License

MIT
