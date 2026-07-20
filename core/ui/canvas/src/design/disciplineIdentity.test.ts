import { describe, it, expect } from 'vitest';
import {
  DISCIPLINES,
  CANVAS_TOKENS,
  canvasTokens,
  disciplineIdentity,
  recipeLabelFor,
  jitterFor,
} from './disciplineIdentity';

describe('DISCIPLINES table', () => {
  const expected = [
    'architecture',
    'security',
    'data',
    'product_strategy',
    'ux',
    'performance',
    'ai_ml',
    'testing',
    'devops',
    'observability',
    'scale',
    'compliance',
    'accessibility',
    'voice',
  ];

  it('contains all 14 expected disciplines', () => {
    for (const key of expected) {
      expect(DISCIPLINES[key]).toBeDefined();
    }
    expect(Object.keys(DISCIPLINES).length).toBe(14);
  });

  it('every entry has non-empty color, glyph, role', () => {
    for (const key of Object.keys(DISCIPLINES)) {
      const entry = DISCIPLINES[key];
      expect(entry.color.length).toBeGreaterThan(0);
      expect(entry.glyph.length).toBeGreaterThan(0);
      expect(entry.role.length).toBeGreaterThan(0);
    }
  });
});

describe('disciplineIdentity()', () => {
  it('returns the security entry for "security"', () => {
    expect(disciplineIdentity('security')).toBe(DISCIPLINES.security);
  });

  it('is case-insensitive', () => {
    expect(disciplineIdentity('SECURITY')).toBe(DISCIPLINES.security);
    expect(disciplineIdentity('SeCuRiTy')).toBe(DISCIPLINES.security);
  });

  it('is trim-tolerant', () => {
    expect(disciplineIdentity('  security  ')).toBe(DISCIPLINES.security);
    expect(disciplineIdentity('\tsecurity\n')).toBe(DISCIPLINES.security);
  });

  it('falls back to voice for unknown lens names', () => {
    expect(disciplineIdentity('nonsense_lens')).toBe(DISCIPLINES.voice);
    expect(disciplineIdentity('')).toBe(DISCIPLINES.voice);
  });
});

describe('recipeLabelFor()', () => {
  it('suffixes "audit" for security and compliance', () => {
    expect(recipeLabelFor('security')).toMatch(/audit$/);
    expect(recipeLabelFor('compliance')).toMatch(/audit$/);
    expect(recipeLabelFor('security')).toBe('Security audit');
  });

  it('suffixes "assessment" for ux and accessibility', () => {
    expect(recipeLabelFor('ux')).toMatch(/assessment$/);
    expect(recipeLabelFor('accessibility')).toMatch(/assessment$/);
  });

  it('suffixes "review" for architecture and testing', () => {
    expect(recipeLabelFor('architecture')).toMatch(/review$/);
    expect(recipeLabelFor('testing')).toMatch(/review$/);
    expect(recipeLabelFor('architecture')).toBe('Architecture review');
  });

  it('suffixes "analysis" for everything else', () => {
    expect(recipeLabelFor('data')).toMatch(/analysis$/);
    expect(recipeLabelFor('performance')).toMatch(/analysis$/);
    expect(recipeLabelFor('observability')).toMatch(/analysis$/);
    expect(recipeLabelFor('data')).toBe('Data analysis');
  });

  it('special-cases ai_ml to "AI/ML"', () => {
    expect(recipeLabelFor('ai_ml')).toBe('AI/ML analysis');
  });

  it('title-cases multi-word lens names', () => {
    expect(recipeLabelFor('product_strategy')).toBe('Product Strategy analysis');
  });
});

describe('jitterFor()', () => {
  it('is deterministic — same inputs return same output', () => {
    const a = jitterFor('run-1', 'security');
    const b = jitterFor('run-1', 'security');
    expect(a).toBe(b);
  });

  it('varies across lens for same run', () => {
    const sec = jitterFor('run-1', 'security');
    const arch = jitterFor('run-1', 'architecture');
    expect(sec).not.toBe(arch);
  });

  it('varies across run for same lens', () => {
    const r1 = jitterFor('run-1', 'security');
    const r2 = jitterFor('run-2', 'security');
    expect(r1).not.toBe(r2);
  });

  it('always returns a value in [-0.6, 0.6]', () => {
    const samples = [
      jitterFor('run-1', 'security'),
      jitterFor('run-1', 'architecture'),
      jitterFor('run-1', 'data'),
      jitterFor('run-1', 'product_strategy'),
      jitterFor('run-1', 'ux'),
      jitterFor('run-2', 'security'),
      jitterFor('run-3', 'security'),
      jitterFor('', ''),
      jitterFor('a', 'b'),
      jitterFor('long-run-id-with-many-chars-1234567890', 'observability'),
    ];
    for (const s of samples) {
      expect(s).toBeGreaterThanOrEqual(-0.6);
      expect(s).toBeLessThanOrEqual(0.6);
    }
  });
});

describe('CANVAS_TOKENS', () => {
  it('paperBg matches spec value #EDE3CC (dark-mode default alias)', () => {
    expect(CANVAS_TOKENS.paperBg).toBe('#EDE3CC');
  });

  it('includes all expected token keys', () => {
    const expected = [
      'paperBg',
      'paperBgGold',
      'paperBgDim',
      'paperInk',
      'paperInkSoft',
      'paperMuted',
      'paperGoldMuted',
      'cardShadow',
      'cardShadowHover',
      'cardShadowDim',
      'synthesisShadow',
      'cardRadius',
      'paperDivider',
      'paperDividerGold',
      'paperFocusRing',
      'arrowChalk',
      'arrowChalkBright',
    ];
    for (const key of expected) {
      expect((CANVAS_TOKENS as Record<string, string>)[key]).toBeDefined();
    }
  });
});

describe('canvasTokens(mode)', () => {
  it('returns the cream/parchment surface for dark mode', () => {
    const tk = canvasTokens('dark');
    expect(tk.paperBg).toBe('#EDE3CC');
    expect(tk.paperInk).toBe('#1F1A14');
  });

  it('returns the walnut/cream-text surface for light mode', () => {
    const tk = canvasTokens('light');
    expect(tk.paperBg).toBe('#2A241D');
    expect(tk.paperInk).toBe('#EDE3CC');
  });

  it('inverts surface and ink between modes (cards contrast on both canvases)', () => {
    const dark = canvasTokens('dark');
    const light = canvasTokens('light');
    // Cream parchment in dark mode is the same cream used as ink on light-mode
    // walnut cards — same paper-cream feel, used as either surface or text
    // depending on which canvas it lives on.
    expect(dark.paperBg).toBe(light.paperInk);
    // Light-mode card surface is in the "dark warm" family (not strictly equal
    // to dark-mode ink — light-mode paper is intentionally a hair warmer for
    // visual hierarchy against the cream text).
    expect(light.paperBg).not.toBe(dark.paperBg);
    expect(light.paperInk).not.toBe(dark.paperInk);
  });

  it('arrow chalk inverts: warm-cream on dark canvas, dark-ink on light canvas', () => {
    const dark = canvasTokens('dark');
    const light = canvasTokens('light');
    // Dark canvas → warm cream chalk (light arrow on dark BG)
    expect(dark.arrowChalk).toMatch(/232, 220, 200/);
    // Light canvas → dark ink (dark arrow on light BG)
    expect(light.arrowChalk).toMatch(/31, 26, 20/);
  });

  it('keeps the same cardRadius across both modes (paper-sticky-note consistency)', () => {
    expect(canvasTokens('dark').cardRadius).toBe(canvasTokens('light').cardRadius);
  });

  it('exports every token key in both modes (no mode-specific gaps)', () => {
    const keys = Object.keys(canvasTokens('dark')) as Array<keyof ReturnType<typeof canvasTokens>>;
    const lightKeys = Object.keys(canvasTokens('light')) as Array<keyof ReturnType<typeof canvasTokens>>;
    expect(keys.sort()).toEqual(lightKeys.sort());
  });
});
