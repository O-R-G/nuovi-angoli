# build-italic.py
# batch italic .ttf builder from in-folder/*.ttf
# open each in glyphs, adjusts instance parameters
# perform slant with parameters below
# export with name + -Italic to in-folder/
# close glyphs file

import GlyphsApp
import math
import os
from AppKit import NSOpenPanel

# -----------------------------------------
# 0. choose folder
# -----------------------------------------

panel = NSOpenPanel.openPanel()
panel.setCanChooseDirectories_(True)
panel.setCanChooseFiles_(False)
panel.setAllowsMultipleSelection_(False)

if panel.runModal() != 1:
    print("No folder selected.")
else:

    folderPath = panel.URL().path()
    files = [f for f in os.listdir(folderPath) if f.endswith(".ttf") and "Italic" not in f]

    for fileName in files:

        filePath = os.path.join(folderPath, fileName)
        print("Processing:", fileName)

        font = Glyphs.open(filePath)
        master = font.masters[0]

        # -----------------------------------------
        # 1. set italic angle
        # -----------------------------------------

        master.italicAngle = 8
        skew = math.tan(math.radians(master.italicAngle))
        originY = master.xHeight / 2.0

        # -----------------------------------------
        # 2. slant outliines
        # -----------------------------------------

        font.disableUpdateInterface()

        # avoid double skew for composite glyphs
        for glyph in font.glyphs:
            layer = glyph.layers[master.id]
            if not layer:
                continue
            if layer.components and not layer.paths:
                continue
            if layer.paths:
                layer.applyTransform((1, 0, 0, 1, 0, -originY))
                layer.applyTransform((1, 0, skew, 1, 0, 0))
                layer.applyTransform((1, 0, 0, 1, 0, originY))

        font.enableUpdateInterface()

        # -----------------------------------------
        # 3. adjust naming
        # -----------------------------------------

        familyName = font.familyName.strip()
        psFamily = familyName.replace(" ", "")

        for instance in font.instances:

            baseStyle = instance.name.replace(" Italic", "").strip()
            instance.name = baseStyle + " Italic"
            instance.isItalic = True

            psStyle = baseStyle.replace(" ", "")
            psName = psFamily + "-" + psStyle + "-Italic"

            # This controls exported filename
            instance.fontName = psName

        # -----------------------------------------
        # 4. export 
        # -----------------------------------------

        for instance in font.instances:
            instance.generate(
                Format=GlyphsApp.TTF,
                FontPath=folderPath
            )

        font.close(ignoreChanges=True)

    print("✔ Batch complete. Italics saved to same folder.")
