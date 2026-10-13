#!/usr/bin/env python3
"""Extract the Dolby (DAX2) speaker tuning from the official Surface Book 2
driver package and convert it into an EasyEffects preset.

Usage:
    python3 extract_dolby_tuning.py [--subsys 1146] [--out "Surface Book 2 Dolby.json"]

Needs: curl, 7z (sudo apt install 7zip). Downloads ~1.9 GB from Microsoft.
"""
import argparse, json, math, os, re, shutil, struct, subprocess, sys, tempfile

MSI_URL = ("https://download.microsoft.com/download/9/4/f/94f7aed2-d3ed-4a60-ab94-a0d078fe6df6/"
           "SurfaceBook2_Win11_22000_23.092.25731.0.msi")
DAP_GUID = "f112024a-fe30-42a8-80ab-8dd825a06f78"
AUDIO_OPTIMIZER = 18  # DAP parameter index holding per-band speaker gains
AUDIO_REGULATOR = 22  # DAP parameter index holding per-band limit thresholds
IEQ_TARGET = 13       # DAP parameter index holding the intelligent EQ target curve
IEQ_AMOUNT = 12       # DAP parameter index holding the intelligent EQ strength (0-16)

# Multiband compressor bands: (split frequency, Dolby band indices it covers).
# Dolby bands: 47, 141, 234, 328, 469, 656, 844, 1031, 1313, 1688, 2250 ... Hz
REGULATOR_BANDS = [(None, [0]), (100, [1, 2]), (280, [3, 4, 5, 6, 7, 8]), (1500, [9]), (2000, None)]


def detect_subsys():
    """Read the Realtek codec subsystem id, e.g. 0x10ec1146 -> '1146'."""
    try:
        with open("/proc/asound/card0/codec#0") as f:
            m = re.search(r"Subsystem Id: 0x10ec([0-9a-f]{4})", f.read())
            return m.group(1).upper() if m else None
    except OSError:
        return None


def extract_inf(workdir):
    msi = os.path.join(workdir, "sb2.msi")
    print("Downloading driver package (~1.9 GB)...")
    subprocess.run(["curl", "-fL", "-o", msi, MSI_URL], check=True)
    subprocess.run(["7z", "x", "-y", "-o" + os.path.join(workdir, "msi"), msi],
                   check=True, stdout=subprocess.DEVNULL)
    os.remove(msi)
    cabdir = os.path.join(workdir, "cab")
    for name in os.listdir(os.path.join(workdir, "msi")):
        if name.endswith(".cab"):
            subprocess.run(["7z", "x", "-y", "-o" + cabdir, os.path.join(workdir, "msi", name)],
                           check=True, stdout=subprocess.DEVNULL)
    for name in os.listdir(cabdir):
        data = open(os.path.join(cabdir, name), "rb").read()
        text = data.decode("utf-16", "ignore") if data[:2] == b"\xff\xfe" else data.decode("latin1")
        if "DAX2Preset" in text and "[Version]" in text:
            return text
    sys.exit("No INF with DAX2 presets found in the package.")


def decode_preset(inf, name):
    """Return {param index: int or list of ints} for one DAX2 preset."""
    inf = re.sub(r"\\\s*\n\s*", "", inf.replace("\r", ""))  # join continuation lines
    pattern = (r"^HKR,InterfaceSetting\\" + re.escape(name) + r"\\EP\\0,\s*\"\{" + DAP_GUID +
               r"\},(\d+)\",\s*0x00000001,\s*(.*)$")
    params = {}
    for m in re.finditer(pattern, inf, re.M | re.I):
        raw = bytes(int(x, 16) for x in re.findall(r"[0-9a-fA-F]{2}", m.group(2)))
        vt = struct.unpack_from("<H", raw)[0]  # PROPVARIANT type: 3 = int, 0x41 = blob
        if vt == 3:
            params[int(m.group(1))] = struct.unpack_from("<i", raw, 8)[0]
        else:
            n = (len(raw) - 8) // 4
            params[int(m.group(1))] = list(struct.unpack("<%di" % n, raw[8:8 + n * 4]))
    if not params:
        sys.exit(f"Preset {name} not found in INF.")
    return params


def bell_q(freqs, i):
    lo = freqs[i - 1] if i > 0 else freqs[0] ** 2 / freqs[1]
    hi = freqs[i + 1] if i < len(freqs) - 1 else freqs[-1] ** 2 / freqs[-2]
    bw = math.log2(hi / lo) / 2
    return round(math.sqrt(2 ** bw) / (2 ** bw - 1), 3)


def build_preset(params):
    # Layout: [nbands, nbands, f0..f19, nbands, L0..L19, nbands, R0..R19, ...]; gains in 1/16 dB
    ao = params[AUDIO_OPTIMIZER]
    n = ao[0]
    freqs = ao[2:2 + n]
    left = ao[3 + n:3 + 2 * n]
    right = ao[4 + 2 * n:4 + 3 * n]

    def side(gains):
        return {f"band{i}": {"frequency": float(freqs[i]), "gain": round(gains[i] / 16, 2),
                             "mode": "RLC (BT)", "mute": False, "q": bell_q(freqs, i),
                             "slope": "x1", "solo": False, "type": "Bell"} for i in range(n)}

    limiter = {"bypass": False, "mode": "Herm Thin", "oversampling": "True Peak/16 bit",
               "dithering": "None", "sidechain-type": "Internal", "threshold": -1.0,
               "attack": 5.0, "release": 10.0, "lookahead": 5.0, "stereo-link": 100.0,
               "input-gain": 0.0, "output-gain": 0.0, "gain-boost": False, "alr": False,
               "alr-attack": 5.0, "alr-knee": 0.0, "alr-knee-smooth": -5.0, "alr-release": 50.0,
               "sidechain-preamp": 0.0, "input-to-link": -80.01, "input-to-sidechain": -80.01,
               "link-to-input": -80.01, "link-to-sidechain": -80.01,
               "sidechain-to-input": -80.01, "sidechain-to-link": -80.01}
    return {"output": {"blocklist": [],
                       "plugins_order": ["equalizer#0", "equalizer#1",
                                         "multiband_compressor#0", "limiter#0"],
                       "equalizer#0": {"bypass": False, "input-gain": 0.0,
                                       "output-gain": 0.0, "mode": "IIR", "num-bands": n,
                                       "split-channels": True,
                                       "left": side(left), "right": side(right)},
                       "equalizer#1": build_ieq(params),
                       "multiband_compressor#0": build_regulator(params),
                       "limiter#0": limiter}}


def build_ieq(params):
    """Approximate Dolby's intelligent EQ with a static equalizer.

    Layout: [n, n, f0..f19, n, target0..target19] in 1/16 dB. The real IEQ is dynamic: it
    pushes the music's spectrum towards this target. Here the target is centred on 0 dB
    (so loudness is unchanged when toggling it) and scaled by the IEQ amount (param 12,
    read as 0-16; this reading is a guess).
    """
    ieq = params[IEQ_TARGET]
    n = ieq[0]
    freqs = ieq[2:2 + n]
    target = [t / 16 for t in ieq[3 + n:3 + 2 * n]]
    mean = sum(target) / n
    amount = params.get(IEQ_AMOUNT, 10) / 16
    bands = {f"band{i}": {"frequency": float(freqs[i]), "gain": round((target[i] - mean) * amount, 2),
                          "mode": "RLC (BT)", "mute": False, "q": bell_q(freqs, i),
                          "slope": "x1", "solo": False, "type": "Bell"} for i in range(n)}
    return {"bypass": False, "input-gain": 0.0, "output-gain": 0.0, "mode": "IIR",
            "num-bands": n, "split-channels": False, "left": bands, "right": dict(bands)}


def build_regulator(params):
    """Approximate Dolby's audio regulator (speaker protection) with a multiband compressor.

    Layout: [n, n, f0..f19, n, high0..high19, n, low0..low19, n, isolated0..isolated19]
    in 1/16 dB. The headphone preset has high = -12 dB / low = 0 dB on every band, i.e. no
    regulation, so "low" is read as the dBFS threshold. This interpretation is a best guess,
    tuned by ear; Dolby does not document the format.
    """
    reg = params[AUDIO_REGULATOR]
    n = reg[0]
    low = reg[4 + 2 * n:4 + 3 * n]

    common = {"attack-time": 5.0, "release-time": 120.0, "ratio": 4.0, "knee": -6.0,
              "makeup": 0.0, "mute": False, "solo": False, "compression-mode": "Downward",
              "release-threshold": -80.01, "boost-amount": 6.0, "boost-threshold": -72.0,
              "sidechain-mode": "Peak", "sidechain-source": "Middle", "sidechain-type": "Internal",
              "sidechain-preamp": 0.0, "sidechain-reactivity": 10.0, "sidechain-lookahead": 0.0,
              "sidechain-custom-lowcut-filter": False, "sidechain-custom-highcut-filter": False,
              "sidechain-lowcut-frequency": 10.0, "sidechain-highcut-frequency": 20000.0,
              "stereo-split-source": "Left/Right"}
    mb = {"bypass": False, "compressor-mode": "Modern", "envelope-boost": "None",
          "input-gain": 0.0, "output-gain": 0.0, "dry": -80.01, "wet": 0.0, "stereo-split": False,
          "input-to-link": -80.01, "input-to-sidechain": -80.01, "link-to-input": -80.01,
          "link-to-sidechain": -80.01, "sidechain-to-input": -80.01, "sidechain-to-link": -80.01}
    for i in range(8):
        band = dict(common)
        if i < len(REGULATOR_BANDS):
            split, idx = REGULATOR_BANDS[i]
            if idx:
                threshold = round(sum(low[j] for j in idx) / len(idx) / 16)
                # Dolby's 47 Hz band (-60 dB) is already cut by the EQ; -40 is enough
                band["attack-threshold"] = float(max(threshold, -40))
                band["compressor-enable"] = True
            else:
                band["attack-threshold"] = 0.0
                band["compressor-enable"] = False
        else:
            split = 2000 * 2 ** (i - len(REGULATOR_BANDS) + 1)
            band.update({"attack-threshold": -12.0, "compressor-enable": True})
        if i > 0:
            band["split-frequency"] = float(split)
            band["enable-band"] = i < len(REGULATOR_BANDS)
        mb[f"band{i}"] = band
    return mb


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subsys", help="codec subsystem id, last 4 hex digits (auto-detected)")
    ap.add_argument("--inf", help="use an already extracted INF instead of downloading")
    ap.add_argument("--out", default="Surface Book 2 Dolby.json")
    args = ap.parse_args()

    subsys = (args.subsys or detect_subsys() or "1146").upper()
    print(f"Codec subsystem: 10EC{subsys}")
    if args.inf:
        data = open(args.inf, "rb").read()
        inf = data.decode("utf-16", "ignore") if data[:2] == b"\xff\xfe" else data.decode("latin1")
    else:
        if not shutil.which("7z"):
            sys.exit("7z not found: sudo apt install 7zip")
        with tempfile.TemporaryDirectory() as tmp:
            inf = extract_inf(tmp)

    params = decode_preset(inf, f"DAX2Preset{subsys}_SPK")
    preset = build_preset(params)
    with open(args.out, "w") as f:
        json.dump(preset, f, indent=4)
    eq = preset["output"]["equalizer#0"]
    for ch in ("left", "right"):
        print(ch.ljust(5), " ".join(f"{b['frequency']:.0f}Hz:{b['gain']:+.1f}" for b in eq[ch].values()))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
