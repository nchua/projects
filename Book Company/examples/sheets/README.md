# Bake-off fixture sheets (SPEC §8.3)

`book bakeoff --sheets examples/sheets/` reads three fixture character sheets from here.
Images are not checked into git (they are generated or drawn, and large); put them here before
running the bake-off. Layout, one folder per character id used in `examples/bakeoff/scenes.yaml`:

```
examples/sheets/
  maya/sheet.png                     # required: the turnaround sheet (or provide crops below)
  maya/sheet_crops/front.png         # optional; preferred as references when present
  maya/sheet_crops/three_quarter.png # optional
  maya/sheet_crops/side.png          # optional
  toast/sheet.png
  pickles/sheet.png
  anchors/*.png                      # optional: 2-3 style anchors in the locked style
```

These are the same names S2 will write under `series/<id>/characters/<id>/`, so a sheet made
for the bake-off can seed the demo series. Until S2 exists, make the three sheets by hand or with
one provider's playground from the appearance card in `examples/family_demo.json` and the
`gouache-warm` style bible, and use the same sheets for every provider (a fair test).
