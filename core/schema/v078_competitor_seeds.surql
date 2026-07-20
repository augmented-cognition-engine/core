-- v078: Pre-seed the competitor registry with Tier 1/2/3 companies.
--
-- Tier 1 (direct): Cursor, Windsurf, GitHub Copilot, Cline, Aider, OpenHands
-- Tier 2 (adjacent): Linear AI, Devin, bolt.new, Replit Agent, Factory AI
-- Tier 3 (aspirational): Cognition, Magic.dev, Poolside
--
-- Uses INSERT IGNORE so re-running this migration is safe.
-- The product field references the platform product record.

INSERT IGNORE INTO competitor [
    -- Tier 1 — direct competitors (weekly scan cadence)
    {
        id: "competitor:cursor",
        product: product:platform,
        name: "Cursor",
        tier: 1,
        domains: ["architecture", "ux", "code_conventions"],
        sources: [
            {type: "changelog", url: "https://www.cursor.com/changelog"},
            {type: "github",    url: "https://github.com/getcursor/cursor"}
        ]
    },
    {
        id: "competitor:windsurf",
        product: product:platform,
        name: "Windsurf",
        tier: 1,
        domains: ["architecture", "ux"],
        sources: [
            {type: "changelog", url: "https://codeium.com/windsurf/updates"}
        ]
    },
    {
        id: "competitor:github_copilot",
        product: product:platform,
        name: "GitHub Copilot",
        tier: 1,
        domains: ["api_design", "integration", "deployment"],
        sources: [
            {type: "changelog", url: "https://github.blog/category/product/"},
            {type: "releases",  url: "https://github.com/features/copilot"}
        ]
    },
    {
        id: "competitor:cline",
        product: product:platform,
        name: "Cline",
        tier: 1,
        domains: ["architecture", "integration"],
        sources: [
            {type: "github",    url: "https://github.com/cline/cline"},
            {type: "changelog", url: "https://github.com/cline/cline/releases"}
        ]
    },
    {
        id: "competitor:aider",
        product: product:platform,
        name: "Aider",
        tier: 1,
        domains: ["architecture", "code_conventions"],
        sources: [
            {type: "github",    url: "https://github.com/paul-gauthier/aider"},
            {type: "changelog", url: "https://aider.chat/CHANGELOG.html"}
        ]
    },
    {
        id: "competitor:openhands",
        product: product:platform,
        name: "OpenHands",
        tier: 1,
        domains: ["architecture", "deployment"],
        sources: [
            {type: "github",    url: "https://github.com/All-Hands-AI/OpenHands"}
        ]
    },

    -- Tier 2 — adjacent competitors (monthly scan cadence)
    {
        id: "competitor:linear_ai",
        product: product:platform,
        name: "Linear AI",
        tier: 2,
        domains: ["business_logic", "product_strategy"],
        sources: [
            {type: "changelog", url: "https://linear.app/changelog"}
        ]
    },
    {
        id: "competitor:devin",
        product: product:platform,
        name: "Devin",
        tier: 2,
        domains: ["deployment", "architecture"],
        sources: [
            {type: "changelog", url: "https://cognition.ai/blog"}
        ]
    },
    {
        id: "competitor:bolt_new",
        product: product:platform,
        name: "bolt.new",
        tier: 2,
        domains: ["ux", "deployment"],
        sources: [
            {type: "changelog", url: "https://bolt.new"}
        ]
    },
    {
        id: "competitor:replit_agent",
        product: product:platform,
        name: "Replit Agent",
        tier: 2,
        domains: ["deployment", "ux"],
        sources: [
            {type: "changelog", url: "https://replit.com/blog"}
        ]
    },
    {
        id: "competitor:factory_ai",
        product: product:platform,
        name: "Factory AI",
        tier: 2,
        domains: ["architecture", "integration"],
        sources: [
            {type: "changelog", url: "https://factory.ai/blog"}
        ]
    },

    -- Tier 3 — aspirational (quarterly scan cadence)
    {
        id: "competitor:cognition",
        product: product:platform,
        name: "Cognition",
        tier: 3,
        domains: ["architecture", "ai_ml"],
        sources: [
            {type: "changelog", url: "https://cognition.ai/blog"}
        ]
    },
    {
        id: "competitor:magic_dev",
        product: product:platform,
        name: "Magic.dev",
        tier: 3,
        domains: ["ai_ml", "architecture"],
        sources: [
            {type: "changelog", url: "https://magic.dev/blog"}
        ]
    },
    {
        id: "competitor:poolside",
        product: product:platform,
        name: "Poolside",
        tier: 3,
        domains: ["ai_ml", "architecture"],
        sources: [
            {type: "changelog", url: "https://poolside.ai/blog"}
        ]
    }
];

-- Update schema version
UPDATE config_entry SET value = '78' WHERE key = 'schema_version';
