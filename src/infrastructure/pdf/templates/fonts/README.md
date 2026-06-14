# Tipografía de marca

Dejá acá los archivos de la fuente de marca (`.ttf` o `.otf`).

WeasyPrint los **incrusta en el PDF** vía `@font-face` (definido en `style.css`),
así el documento se ve igual en cualquier PC sin instalar nada.

## Qué pesos hacen falta (idealmente)

- `BrandFont-Regular.ttf`  — texto normal
- `BrandFont-Bold.ttf`     — negritas y títulos
- (opcional) `BrandFont-Light.ttf`, `BrandFont-SemiBold.ttf`, `BrandFont-Italic.ttf`

Una vez que estén acá, se referencian en `style.css` con:

```css
@font-face {
  font-family: "BrandFont";
  src: url(fonts/BrandFont-Regular.ttf);
  font-weight: normal;
}
```

> Los nombres de archivo reales se ajustan según la fuente que uses.
