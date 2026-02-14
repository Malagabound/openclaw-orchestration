#!/usr/bin/env node
/**
 * Customize a cloned micro-SaaS template with product-specific content.
 * Usage: node customize.js <project_dir> '<product_config_json>'
 * Example: node customize.js /home/milad/markdown-magic '{"name":"MarkdownMagic",...}'
 */

const fs = require("fs");
const path = require("path");

const projectDir = process.argv[2];
const configJson = process.argv[3];

if (!projectDir || !configJson) {
  console.error("Usage: node customize.js <project_dir> '<product_config_json>'");
  process.exit(1);
}

let config;
try {
  config = JSON.parse(configJson);
} catch (e) {
  // Try reading from file path
  try {
    config = JSON.parse(fs.readFileSync(configJson, "utf8"));
  } catch (e2) {
    console.error("Failed to parse config JSON:", e.message);
    process.exit(1);
  }
}

function readFile(relPath) {
  return fs.readFileSync(path.join(projectDir, relPath), "utf8");
}

function writeFile(relPath, content) {
  const fullPath = path.join(projectDir, relPath);
  fs.mkdirSync(path.dirname(fullPath), { recursive: true });
  fs.writeFileSync(fullPath, content, "utf8");
  console.log(`  Updated: ${relPath}`);
}

function replaceInFile(relPath, replacements) {
  let content = readFile(relPath);
  for (const [search, replace] of replacements) {
    content = content.replace(search, replace);
  }
  writeFile(relPath, content);
}

console.log(`\nCustomizing ${projectDir} for "${config.name}"...\n`);

// 1. package.json — update name
try {
  const pkg = JSON.parse(readFile("package.json"));
  pkg.name = config.slug;
  writeFile("package.json", JSON.stringify(pkg, null, 2) + "\n");

  // Add any extra npm packages from config
  if (config.tool?.npm_packages && config.tool.npm_packages.length > 0) {
    console.log(`  Extra packages needed: ${config.tool.npm_packages.join(", ")}`);
    for (const dep of config.tool.npm_packages) {
      pkg.dependencies = pkg.dependencies || {};
      pkg.dependencies[dep] = "latest";
    }
    writeFile("package.json", JSON.stringify(pkg, null, 2) + "\n");
  }
} catch (e) {
  console.error("Failed to update package.json:", e.message);
}

// 2. src/lib/utils.ts — APP_NAME, API key prefix, PLANS
try {
  let utils = readFile("src/lib/utils.ts");

  // Replace APP_NAME default
  utils = utils.replace(
    /export const APP_NAME = process\.env\.NEXT_PUBLIC_APP_NAME \|\| "ConvertFlow"/,
    `export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME || "${config.name}"`
  );

  // Replace API key prefix
  utils = utils.replace(/let key = "cf_"/, `let key = "${config.api_key_prefix}"`);

  // Replace PLANS if config provides them
  if (config.plans) {
    const freePlan = config.plans.free || {};
    const proPlan = config.plans.pro || {};
    utils = utils.replace(
      /conversionsPerDay: 10,/,
      `conversionsPerDay: ${freePlan.conversions_per_day || 10},`
    );
    utils = utils.replace(
      /maxFileSize: 1 \* 1024 \* 1024,/,
      `maxFileSize: ${(freePlan.max_file_mb || 1)} * 1024 * 1024,`
    );
    utils = utils.replace(
      /price: 19,/,
      `price: ${proPlan.price || 19},`
    );
    utils = utils.replace(
      /maxFileSize: 50 \* 1024 \* 1024,/,
      `maxFileSize: ${(proPlan.max_file_mb || 50)} * 1024 * 1024,`
    );
  }

  writeFile("src/lib/utils.ts", utils);
} catch (e) {
  console.error("Failed to update utils.ts:", e.message);
}

// 3. src/lib/converter.ts — Replace entirely with generated code
try {
  if (config.tool?.converter_code) {
    writeFile("src/lib/converter.ts", config.tool.converter_code);
  } else {
    console.log("  WARN: No converter_code in config, keeping original");
  }
} catch (e) {
  console.error("Failed to update converter.ts:", e.message);
}

// 4. src/app/page.tsx — Hero section and features
try {
  let page = readFile("src/app/page.tsx");

  // Replace hero title
  if (config.hero?.title_html) {
    page = page.replace(
      /Convert\{" "\}\s*\n\s*<span className="text-primary">JSON<\/span>\s*\n\s*\{" "\}&amp;\{" "\}\s*\n\s*<span className="text-primary">CSV<\/span>\s*\n\s*\{" "\}Instantly/s,
      config.hero.title_html
    );
  }

  // Replace subtitle
  if (config.hero?.subtitle) {
    page = page.replace(
      /Paste, convert, download\. The fastest way to transform data between JSON and CSV formats\.\s*Free for 10 conversions\/day, or upgrade for unlimited access \+ API\./s,
      config.hero.subtitle
    );
  }

  // Replace badge text
  if (config.hero?.badge) {
    page = page.replace(
      /Free to use &mdash; no signup required/,
      config.hero.badge
    );
  }

  // Replace feature cards
  if (config.features && config.features.length === 4) {
    const featureArrayRegex = /\{?\[[\s\S]*?"Instant Conversion"[\s\S]*?"Handle Any Format"[\s\S]*?\]\.map/;
    const newFeatures = `{[
              {
                icon: ${config.features[0].icon},
                title: "${config.features[0].title}",
                desc: "${config.features[0].desc}",
              },
              {
                icon: ${config.features[1].icon},
                title: "${config.features[1].title}",
                desc: "${config.features[1].desc}",
              },
              {
                icon: ${config.features[2].icon},
                title: "${config.features[2].title}",
                desc: "${config.features[2].desc}",
              },
              {
                icon: ${config.features[3].icon},
                title: "${config.features[3].title}",
                desc: "${config.features[3].desc}",
              },
            ].map`;
    page = page.replace(featureArrayRegex, newFeatures);
  }

  writeFile("src/app/page.tsx", page);
} catch (e) {
  console.error("Failed to update page.tsx:", e.message);
}

// 5. src/app/pricing/page.tsx — Plans and features
try {
  let pricing = readFile("src/app/pricing/page.tsx");

  // Replace Pro price
  if (config.plans?.pro?.price) {
    pricing = pricing.replace(/price: "\$19"/, `price: "$${config.plans.pro.price}"`);
    pricing = pricing.replace(
      /just \$19\/month/,
      `just $${config.plans.pro.price}/month`
    );
  }

  // Replace plan descriptions
  if (config.tagline) {
    pricing = pricing.replace(
      /Perfect for quick one-off conversions/,
      `Perfect for quick ${config.tagline.toLowerCase()}`
    );
  }

  // Replace free features list
  if (config.pricing_features?.free) {
    const freeFeatures = config.pricing_features.free
      .map((f) => `      "${f}",`)
      .join("\n");
    pricing = pricing.replace(
      /features: \[\s*"10 conversions per day"[\s\S]*?"Copy & download output",\s*\]/,
      `features: [\n${freeFeatures}\n    ]`
    );
  }

  // Replace pro features list
  if (config.pricing_features?.pro) {
    const proFeatures = config.pricing_features.pro
      .map((f) => `      "${f}",`)
      .join("\n");
    pricing = pricing.replace(
      /features: \[\s*"Unlimited conversions"[\s\S]*?"Priority support",\s*\]/,
      `features: [\n${proFeatures}\n    ]`
    );
  }

  writeFile("src/app/pricing/page.tsx", pricing);
} catch (e) {
  console.error("Failed to update pricing/page.tsx:", e.message);
}

// 6. src/components/landing/hero-converter.tsx — Sample data and labels
try {
  let hero = readFile("src/components/landing/hero-converter.tsx");

  // Replace imports — use new converter functions
  hero = hero.replace(
    /import \{ jsonToCsv, csvToJson, detectFormat \} from "@\/lib\/converter"/,
    `import { convertForward, convertBackward, detectFormat } from "@/lib/converter"`
  );

  // Replace sample data
  if (config.tool?.sample_input) {
    const escapedInput = config.tool.sample_input.replace(/`/g, "\\`").replace(/\$/g, "\\$");
    hero = hero.replace(
      /const SAMPLE_JSON = `[\s\S]*?`;/,
      `const SAMPLE_JSON = \`${escapedInput}\`;`
    );
  }

  if (config.tool?.sample_output) {
    const escapedOutput = config.tool.sample_output.replace(/`/g, "\\`").replace(/\$/g, "\\$");
    hero = hero.replace(
      /const SAMPLE_CSV = `[\s\S]*?`;/,
      `const SAMPLE_CSV = \`${escapedOutput}\`;`
    );
  }

  // Replace direction types
  const dir0 = config.tool?.directions?.[0] || "forward";
  const dir1 = config.tool?.directions?.[1] || "backward";
  hero = hero.replace(/"json_to_csv" \| "csv_to_json"/g, `"${dir0}" | "${dir1}"`);
  hero = hero.replace(/"json_to_csv"/g, `"${dir0}"`);
  hero = hero.replace(/"csv_to_json"/g, `"${dir1}"`);

  // Replace conversion function calls
  hero = hero.replace(/jsonToCsv\(input\)/g, "convertForward(input)");
  hero = hero.replace(/csvToJson\(input\)/g, "convertBackward(input)");

  // Replace labels
  const inputLabel = config.tool?.input_label || "INPUT";
  const outputLabel = config.tool?.output_label || "OUTPUT";
  hero = hero.replace(/JSON Input/g, inputLabel.replace(" INPUT", " Input"));
  hero = hero.replace(/CSV Input/g, outputLabel.replace(" OUTPUT", " Input"));
  hero = hero.replace(/JSON/g, inputLabel.replace(" INPUT", ""));
  hero = hero.replace(/CSV/g, outputLabel.replace(" OUTPUT", ""));
  hero = hero.replace(/Paste your JSON here\.\.\./g, `Paste your ${inputLabel.toLowerCase().replace(" input", "")} here...`);
  hero = hero.replace(/Paste your CSV here\.\.\./g, `Paste your ${outputLabel.toLowerCase().replace(" output", "")} here...`);

  writeFile("src/components/landing/hero-converter.tsx", hero);
} catch (e) {
  console.error("Failed to update hero-converter.tsx:", e.message);
}

// 7. src/components/ui/navbar.tsx — Logo initials
try {
  if (config.initials) {
    replaceInFile("src/components/ui/navbar.tsx", [
      ["CF", config.initials],
    ]);
  }
} catch (e) {
  console.error("Failed to update navbar.tsx:", e.message);
}

// 8. src/app/api/v1/convert/route.ts — Direction handling
try {
  let route = readFile("src/app/api/v1/convert/route.ts");

  // Replace converter imports
  route = route.replace(
    /import \{ jsonToCsv, csvToJson \} from "@\/lib\/converter"/,
    `import { convertForward, convertBackward } from "@/lib/converter"`
  );

  // Replace direction logic
  const dir0 = config.tool?.directions?.[0] || "forward";
  const dir1 = config.tool?.directions?.[1] || "backward";
  route = route.replace(/"json_to_csv"/g, `"${dir0}"`);
  route = route.replace(/"csv_to_json"/g, `"${dir1}"`);
  route = route.replace(/jsonToCsv\(/g, "convertForward(");
  route = route.replace(/csvToJson\(/g, "convertBackward(");

  // Replace format checks
  route = route.replace(
    /\["csv", "json"\]/,
    `["${config.tool?.output_formats?.[0] || "output1"}", "${config.tool?.output_formats?.[1] || "output2"}"]`
  );

  // Update service name
  route = route.replace(/ConvertFlow API/, `${config.name} API`);

  writeFile("src/app/api/v1/convert/route.ts", route);
} catch (e) {
  console.error("Failed to update convert/route.ts:", e.message);
}

// 9. src/lib/supabase.ts — Direction type
try {
  let supabase = readFile("src/lib/supabase.ts");
  const dir0 = config.tool?.directions?.[0] || "forward";
  const dir1 = config.tool?.directions?.[1] || "backward";
  supabase = supabase.replace(
    /"json_to_csv" \| "csv_to_json"/g,
    `"${dir0}" | "${dir1}"`
  );
  writeFile("src/lib/supabase.ts", supabase);
} catch (e) {
  console.error("Failed to update supabase.ts:", e.message);
}

// 10. supabase/schema.sql — Direction CHECK constraint
try {
  if (config.db_directions_enum) {
    replaceInFile("supabase/schema.sql", [
      [
        "direction IN ('json_to_csv', 'csv_to_json')",
        `direction IN (${config.db_directions_enum})`,
      ],
    ]);
  }

  // Update comments
  replaceInFile("supabase/schema.sql", [
    ["-- ConvertFlow Database Schema", `-- ${config.name} Database Schema`],
  ]);
} catch (e) {
  console.error("Failed to update schema.sql:", e.message);
}

// 11. .env.local.example — APP_NAME
try {
  replaceInFile(".env.local.example", [
    ["NEXT_PUBLIC_APP_NAME=ConvertFlow", `NEXT_PUBLIC_APP_NAME=${config.name}`],
  ]);
} catch (e) {
  console.error("Failed to update .env.local.example:", e.message);
}

console.log(`\nCustomization complete for "${config.name}"!`);
console.log("CUSTOMIZE_SUCCESS");
