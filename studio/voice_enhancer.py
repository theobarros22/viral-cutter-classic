"""Presets locais de limpeza e aprimoramento de voz."""


PRESETS = {
    "light": "highpass=f=70,lowpass=f=15000,afftdn=nf=-28,loudnorm=I=-16:TP=-1.5:LRA=11",
    "podcast": "highpass=f=80,lowpass=f=14000,afftdn=nf=-32,acompressor=threshold=-18dB:ratio=3:attack=20:release=180:makeup=2,loudnorm=I=-16:TP=-1.5:LRA=9",
    "strong": "highpass=f=90,lowpass=f=12500,anlmdn=s=0.002:p=0.01:r=0.02,afftdn=nf=-38,acompressor=threshold=-20dB:ratio=4:attack=15:release=220:makeup=3,loudnorm=I=-15:TP=-1.2:LRA=7",
}


def filtro_voz(preset):
    if preset not in PRESETS:
        raise ValueError("Preset de voz invalido.")
    return PRESETS[preset]
