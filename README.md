# Synthetic Color Channel (Siril script)

Creates a synthetic red, green, blue or luminance channel for a color image from a formula you choose (e.g. `2*g - b`), and either replaces that channel in the RGB image or produces a luminance image.

<img width="472" height="274" alt="screenshot-010" src="https://github.com/user-attachments/assets/03902a2b-9338-43a0-8461-cb323c2dd80c" />


## What it is good for

- Planetary imaging with achromats, strong defocus and lower optical quality, which often show up mainly in the blue channel.
- Filling in a missing color channel in an RGB composition.
- Converting an OSC image to luminance with better SNR than simply setting saturation to 0.

## How to use

1. If you have not done so yet, create a folder for your own Siril scripts, e.g. `C:\Users\<you>\my_siril_scripts` (Windows) or `/home/<you>/my_siril_scripts`.
2. Copy `synth_color_channel.py` into that folder.
3. Restart Siril.

The script then appears in Siril's script menu. Select a target channel, pick a preset or type your own formula, and press **Apply**. Batch processing of several files is available in the collapsible *Batch Processing* section.

Allowed in formulas: variables `r`, `g`, `b` (case-insensitive), the operators `+ - * / **`, parentheses, and the functions `sin, cos, tan, asin, acos, atan, sinh, cosh, tanh, asinh, acosh, atanh, log, log10, log2, sqrt, abs, exp`. Implicit multiplication (`2g`, `2(r+g)`) works as well.

Tested on Siril 1.4.5.

Feedback, ideas, bug reports and pull requests are welcome.
