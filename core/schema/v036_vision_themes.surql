-- v036: Direction → Vision + Themes
-- Vision is just name + description (no goals).
-- Theme is a strategic bet that groups initiatives.

-- Replace product_direction with product_vision
REMOVE TABLE IF EXISTS product_direction;
DEFINE TABLE product_vision SCHEMALESS;
DEFINE FIELD org ON product_vision TYPE record<org>;
DEFINE FIELD name ON product_vision TYPE string;
DEFINE FIELD description ON product_vision TYPE string DEFAULT "";
DEFINE FIELD active ON product_vision TYPE bool DEFAULT true;
DEFINE FIELD supersedes ON product_vision TYPE option<record<product_vision>>;
DEFINE FIELD created_at ON product_vision TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_vision_org ON product_vision FIELDS org;
DEFINE INDEX idx_vision_active ON product_vision FIELDS org, active;

-- Theme: strategic bet between vision and initiatives
DEFINE TABLE theme SCHEMALESS;
DEFINE FIELD org ON theme TYPE record<org>;
DEFINE FIELD name ON theme TYPE string;
DEFINE FIELD description ON theme TYPE string DEFAULT "";
DEFINE FIELD status ON theme TYPE string DEFAULT "active";
DEFINE FIELD created_at ON theme TYPE datetime DEFAULT time::now();
DEFINE INDEX idx_theme_org ON theme FIELDS org;
DEFINE INDEX idx_theme_status ON theme FIELDS org, status;

-- Add optional theme reference to initiative
DEFINE FIELD theme ON initiative TYPE option<record<theme>>;

UPDATE config_entry SET value = '36' WHERE key = 'schema_version';
