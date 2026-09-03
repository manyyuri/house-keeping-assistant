# 生图提示词模板

将此模板与菜谱内容结合，生成最终的AI绘图提示词。

---

## 风格选择

| 风格 | 名称 | 特点 | 适用场景 |
|------|------|------|----------|
| **风格C（默认）** | 现代写实风 | 横版16:9，现代、写实、教育感强 | 专业教程、出版级菜谱 |
| **风格A** | 传统海报风 | 竖版2:3，装饰丰富，视觉冲击强 | 社交媒体、印刷海报 |
| **风格B** | 文人卷轴风 | 横版16:9，素雅内敛，以文字为主 | 高端呈现、收藏级文档 |

**使用规则**：
- 默认使用 **风格C**
- 用户指定"风格A"时使用传统海报风模板
- 用户指定"风格B"时使用文人卷轴风模板

---

## 风格C：现代写实风（默认）

```
A modern, realistic culinary infographic poster,
presenting the complete professional recipe of
《{{菜名}} · 顶级配方》.

OVERALL STYLE:
High-end modern culinary editorial combined with professional cooking instruction.
Clean, precise, realistic, restrained.
Feels like a culinary institute teaching board or Michelin test kitchen manual.
Educational clarity is the primary goal.

LANGUAGE & TEXT QUALITY (ABSOLUTE PRIORITY):
All text must be in standard simplified Chinese only.
High-definition, print-quality Chinese characters.
No traditional Chinese.
No misspellings.
No incorrect or distorted characters.
No pseudo-text.

IMPORTANT TEXT RULES:
All text must be rendered as natural printed book text.
Do NOT display any markdown symbols or formatting characters.
Do NOT show characters such as:
#, ##, ###, -, *, |, >, ``` or bullet symbols.
Section hierarchy must be expressed through layout, spacing, font size, and alignment only.

If needed, rewrite structured content into clean natural language paragraphs or aligned tables.

BACKGROUND:
Clean neutral background with subtle texture
(light warm gray or off-white).
Soft even studio lighting.
No patterns, no decorative backgrounds.
High contrast for long readable text.

TYPOGRAPHY:
Main title in modern, bold, highly legible Chinese typography.
Section titles in slightly larger or heavier font weight.
Body text in clean professional Chinese type.
Comfortable line spacing for dense instructional content.
Tables must be clean, aligned, and grid-based without ASCII characters.

LAYOUT STRUCTURE (CRITICAL):
Aspect ratio 16:9.
Double-row horizontal layout with clear blank space separating rows.
Strict grid system.
Visual separation achieved through spacing and alignment, not symbols.

UPPER ROW CONTENT (VISUAL SECTIONS):
Dish introduction (origin, flavor profile, serving context).
Ingredient lists grouped logically (main ingredients, secondary ingredients, seasonings).
Core principles or key logic summarized in short, readable statements.

LOWER ROW CONTENT (VISUAL SECTIONS):
Preparation work and tools.
Cooking process divided into stages with time and heat control.
Critical checkpoints, warnings, and professional tips.
Final quality standards and common questions.

IMAGERY (REALISTIC, EDUCATIONAL):
High-quality realistic food photography:
raw ingredients,
key cooking stages,
final result with clean professional plating.
Images must support understanding, not distract.

GRAPHIC ELEMENTS (FUNCTIONAL ONLY):
Minimal modern diagrams:
time indicators,
heat level markers,
process flow arrows.
Flat, technical style.
No decorative icons.

COLOR SYSTEM:
Neutral professional palette:
black, dark gray, warm gray, off-white.
One restrained accent color for emphasis only.
No bright or playful colors.

STRICT EXCLUSIONS:
No markdown characters.
No bullet symbols.
No decorative-only graphics.
No cultural motifs.
No cluttered collage.
No illegible characters.

FINAL RULE:
Render the content exactly like a professionally typeset cookbook page,
not a markdown document or note file.

--ar 16:9 --v 6.1 --q 2 高清简体中文
```

---

## 风格A：传统海报风

```
A high-quality vertical educational infographic poster in a traditional Chinese retro style,
designed for 《{{菜名}} 顶级配方》 by 大师秘籍.

BACKGROUND & MATERIAL:
Soft radial vignette on aged rice paper with visible fiber texture,
faint tea-stain marks,
subtle watermark of Song-dynasty culinary vessel at 8% opacity.
Warm ivory base (#F9F5EC).
Elegant ink-wash atmosphere, print-ready, museum-grade texture.

TYPOGRAPHY SYSTEM:
All body text in Noto Serif CJK SC (思源宋体), high legibility.
Primary titles in bold Chinese calligraphy (Yan Zhenqing style).
Secondary headers in refined semi-cursive (Xingshu).
Author signature in small seal script.

COLOR PALETTE (Elegant Ink):
Ink black, vermilion (#C3272B), celadon (#8BAF98),
amber (#D4A017), rice paper white.
Low saturation, restrained, traditional Chinese aesthetics.

LAYOUT PRINCIPLES:
Vertical aspect ratio 2:3.
40% negative space, generous padding.
Top-heavy title, middle instructional emphasis,
bottom 30% visually led by icons and process illustrations.
Clear visual hierarchy, no clutter, editorial layout quality.

RECIPE CONTENT HIGHLIGHTS:
- Main ingredients: [主要食材列表]
- Key technique: [核心技法]
- Distinctive flavor: [风味特点]
- Cooking time: [烹饪时间]

DECORATIVE ELEMENTS (SUBTLE):
Ruyi clouds, auspicious motifs, seal marks, ink borders.
Opacity strictly controlled (5–12%).
Decoration must support information, never decorative-only.

IMAGE QUALITY:
Ultra-high resolution, studio lighting for food elements,
sharp focus, no blur, no distortion, no pixelation.
Educational + collectible poster quality.

STRICT EXCLUSIONS:
No Western utensils.
No modern appliances unless explicitly required by recipe.
No illegible characters.
No excessive text density.
No irrelevant decorative graphics.

--ar 16:9 --v 6.1 --q 2 --style raw
```

---

## 风格B：文人卷轴风

```
A refined Chinese literati-style culinary infographic,
designed as a classical horizontal recipe manuscript scroll,
presenting the complete recipe of
《{{菜名}} · 顶级配方》.

OVERALL STYLE:
Traditional Chinese literati culinary manuscript.
Horizontal scroll reading experience.
Calm, scholarly, restrained, archival.
Text-first composition with subtle supporting illustrations.
Feels like a well-preserved hand-copied cooking scroll.

LANGUAGE & TEXT QUALITY (ABSOLUTE PRIORITY):
All text must be in standard simplified Chinese only.
High-definition, print-quality Chinese characters.
No traditional Chinese characters.
No misspellings.
No incorrect or distorted characters.
No pseudo-text.
Text accuracy and legibility override all visual effects.

BACKGROUND:
Warm ivory handmade rice paper texture.
Extremely subtle fiber grain.
Soft ink-wash gradients near the left and right edges only.
Large horizontal breathing space.
Quiet, timeless, breathable.

TYPOGRAPHY:
Main title in restrained, dignified Chinese calligraphy,
placed slightly left of center.
Readable, scholarly, not expressive.
Body text in classical Song-style serif Chinese.
Vertical text columns are allowed but arranged left-to-right.
Generous line spacing.
Clear paragraph rhythm.
Resembles annotated manuscript scroll pages.

LAYOUT STRUCTURE:
Horizontal scroll-inspired layout.
Aspect ratio 16:9.
Multiple vertical text columns flowing from left to right.
Asymmetrical but balanced composition.
No boxed sections, no frames.
Sections separated by spacing and rhythm only.

CONTENT ORGANIZATION (VISUAL FLOW):
From left to right:
- Dish introduction and flavor logic
- Ingredient ratios and seasoning composition
- Key preparation techniques
- Cooking time and heat control
- Slicing, resting, or finishing notes

Small vertical headings mark transitions.
Text reads continuously like a scroll.

GRAPHIC ELEMENTS (VERY SUBTLE):
Small ink-style illustrations used as visual pauses:
- Aromatic spices
- Main protein symbol
- Simple cookware sketches
Flat, minimal, monochrome.
Secondary to text.
No realism, no shading.

COLOR SYSTEM:
Ink black dominant.
Very light vermilion used sparingly for seals, stamps, or emphasis.
Overall near-monochrome.

DECORATION:
Minimal seal stamps near the title or section breaks.
Occasional light brush dividers only when text naturally pauses.
No decorative patterns.
No borders.

RULE:
Text is the hero.
Illustrations serve reading rhythm.
Beauty through restraint.
Nothing loud.
Nothing modern.

--ar 16:9 --v 6.1 --q 2 高清简体中文
Text accuracy is more important than visual complexity.
If necessary, simplify graphics to preserve text clarity.
```

---

## 使用说明

1. **替换变量**：将 `{{菜名}}` 替换为实际的菜品名称

2. **风格A增强**：填充 `RECIPE CONTENT HIGHLIGHTS` 部分的内容

3. **输出格式**：
   - 风格C：英文格式，仅菜名使用中文，强调无Markdown符号
   - 风格A：英文格式，仅菜名使用中文
   - 风格B：保持原格式，强调简体中文文字清晰度

---

## 示例输出

### 风格C示例（红烧肉 - 默认）

```
A modern, realistic culinary infographic poster,
presenting the complete professional recipe of
《红烧肉 · 顶级配方》.

OVERALL STYLE:
High-end modern culinary editorial combined with professional cooking instruction.
Clean, precise, realistic, restrained.
Feels like a culinary institute teaching board or Michelin test kitchen manual.
Educational clarity is the primary goal.

LANGUAGE & TEXT QUALITY (ABSOLUTE PRIORITY):
All text must be in standard simplified Chinese only.
High-definition, print-quality Chinese characters.
No traditional Chinese.
No misspellings.
No incorrect or distorted characters.
No pseudo-text.

IMPORTANT TEXT RULES:
All text must be rendered as natural printed book text.
Do NOT display any markdown symbols or formatting characters.
Do NOT show characters such as:
#, ##, ###, -, *, |, >, ``` or bullet symbols.
Section hierarchy must be expressed through layout, spacing, font size, and alignment only.

If needed, rewrite structured content into clean natural language paragraphs or aligned tables.

BACKGROUND:
Clean neutral background with subtle texture
(light warm gray or off-white).
Soft even studio lighting.
No patterns, no decorative backgrounds.
High contrast for long readable text.

TYPOGRAPHY:
Main title in modern, bold, highly legible Chinese typography.
Section titles in slightly larger or heavier font weight.
Body text in clean professional Chinese type.
Comfortable line spacing for dense instructional content.
Tables must be clean, aligned, and grid-based without ASCII characters.

LAYOUT STRUCTURE (CRITICAL):
Aspect ratio 16:9.
Double-row horizontal layout with clear blank space separating rows.
Strict grid system.
Visual separation achieved through spacing and alignment, not symbols.

UPPER ROW CONTENT (VISUAL SECTIONS):
Dish introduction (origin, flavor profile, serving context).
Ingredient lists grouped logically (main ingredients, secondary ingredients, seasonings).
Core principles or key logic summarized in short, readable statements.

LOWER ROW CONTENT (VISUAL SECTIONS):
Preparation work and tools.
Cooking process divided into stages with time and heat control.
Critical checkpoints, warnings, and professional tips.
Final quality standards and common questions.

IMAGERY (REALISTIC, EDUCATIONAL):
High-quality realistic food photography:
raw ingredients,
key cooking stages,
final result with clean professional plating.
Images must support understanding, not distract.

GRAPHIC ELEMENTS (FUNCTIONAL ONLY):
Minimal modern diagrams:
time indicators,
heat level markers,
process flow arrows.
Flat, technical style.
No decorative icons.

COLOR SYSTEM:
Neutral professional palette:
black, dark gray, warm gray, off-white.
One restrained accent color for emphasis only.
No bright or playful colors.

STRICT EXCLUSIONS:
No markdown characters.
No bullet symbols.
No decorative-only graphics.
No cultural motifs.
No cluttered collage.
No illegible characters.

FINAL RULE:
Render the content exactly like a professionally typeset cookbook page,
not a markdown document or note file.

--ar 16:9 --v 6.1 --q 2 高清简体中文
```
