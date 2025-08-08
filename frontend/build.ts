#!/usr/bin/env bun
import plugin from "bun-plugin-tailwind";
import { existsSync, cpSync, readFileSync, writeFileSync } from "fs";
import { rm } from "fs/promises";
import path from "path";

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`
🏗️  Bun Build Script for React

Usage: bun run build.ts [options]

Common Options:
  --outdir <path>          Output directory (default: "dist")
  --minify                 Enable minification (or --minify.whitespace, --minify.syntax, etc)
  --sourcemap <type>      Sourcemap type: none|linked|inline|external
  --target <target>        Build target: browser|bun|node
  --format <format>        Output format: esm|cjs|iife
  --splitting              Enable code splitting
  --packages <type>        Package handling: bundle|external
  --public-path <path>     Public path for assets
  --env <mode>             Environment handling: inline|disable|prefix*
  --conditions <list>      Package.json export conditions (comma separated)
  --external <list>        External packages (comma separated)
  --banner <text>          Add banner text to output
  --footer <text>          Add footer text to output
  --define <obj>           Define global constants (e.g. --define.VERSION=1.0.0)
  --help, -h               Show this help message

Example:
  bun run build.ts --outdir=dist --minify --sourcemap=linked --external=react,react-dom
`);
  process.exit(0);
}

const toCamelCase = (str: string): string => str.replace(/-([a-z])/g, g => g[1].toUpperCase());

const parseValue = (value: string): any => {
  if (value === "true") return true;
  if (value === "false") return false;

  if (/^\d+$/.test(value)) return parseInt(value, 10);
  if (/^\d*\.\d+$/.test(value)) return parseFloat(value);

  if (value.includes(",")) return value.split(",").map(v => v.trim());

  return value;
};

function parseArgs(): Partial<Bun.BuildConfig> {
  const config: Partial<Bun.BuildConfig> = {};
  const args = process.argv.slice(2);

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === undefined) continue;
    if (!arg.startsWith("--")) continue;

    if (arg.startsWith("--no-")) {
      const key = toCamelCase(arg.slice(5));
      config[key] = false;
      continue;
    }

    if (!arg.includes("=") && (i === args.length - 1 || args[i + 1]?.startsWith("--"))) {
      const key = toCamelCase(arg.slice(2));
      config[key] = true;
      continue;
    }

    let key: string;
    let value: string;

    if (arg.includes("=")) {
      [key, value] = arg.slice(2).split("=", 2) as [string, string];
    } else {
      key = arg.slice(2);
      value = args[++i] ?? "";
    }

    key = toCamelCase(key);

    if (key.includes(".")) {
      const [parentKey, childKey] = key.split(".");
      config[parentKey] = config[parentKey] || {};
      config[parentKey][childKey] = parseValue(value);
    } else {
      config[key] = parseValue(value);
    }
  }

  return config;
}

const formatFileSize = (bytes: number): string => {
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  return `${size.toFixed(2)} ${units[unitIndex]}`;
};

console.log("\n🚀 Starting React build process...\n");

const cliConfig = parseArgs();
const outdir = cliConfig.outdir || path.join(process.cwd(), "dist");

if (existsSync(outdir)) {
  console.log(`🗑️ Cleaning previous build at ${outdir}`);
  await rm(outdir, { recursive: true, force: true });
}

const start = performance.now();

// React entry point instead of HTML scanning
const entrypoint = path.resolve("src", "main.tsx");
if (!existsSync(entrypoint)) {
  console.error("❌ Entry point not found: src/main.tsx");
  process.exit(1);
}

console.log(`📦 Building React app from ${path.relative(process.cwd(), entrypoint)}\n`);

const result = await Bun.build({
  entrypoints: [entrypoint],
  outdir,
  plugins: [plugin],
  minify: process.env.NODE_ENV === "production" || cliConfig.minify || false,
  target: "browser",
  format: "esm",
  splitting: true,
  sourcemap: process.env.NODE_ENV !== "production" ? "external" : "none",
  define: {
    "process.env.NODE_ENV": JSON.stringify(process.env.NODE_ENV || "production"),
  },
  ...cliConfig,
});

if (!result.success) {
  console.error("❌ Build failed:");
  for (const message of result.logs) {
    console.error(message);
  }
  process.exit(1);
}

// Copy public directory to dist
const publicDir = path.resolve("public");
if (existsSync(publicDir)) {
  console.log("📁 Copying public files...");
  cpSync(publicDir, outdir, { recursive: true });
} else {
  console.warn("⚠️  No public directory found to copy");
}

// Update HTML file to reference built JS
const htmlPath = path.join(outdir, "index.html");
if (existsSync(htmlPath)) {
  console.log("🔗 Updating HTML references...");
  let html = readFileSync(htmlPath, "utf-8");

  // Find the main JS file in the build output
  const mainJsFile = result.outputs.find(output =>
    output.path.includes("main") && output.path.endsWith(".js")
  );

  if (mainJsFile) {
    const jsFileName = path.basename(mainJsFile.path);
    html = html.replace(
      '<script type="module" src="/src/main.tsx"></script>',
      `<script type="module" src="/${jsFileName}"></script>`
    );
    writeFileSync(htmlPath, html);
    console.log(`✅ Updated HTML to reference /${jsFileName}`);
  } else {
    console.warn("⚠️  Could not find main JS file to update HTML reference");
  }
} else {
  console.warn("⚠️  No index.html found in output directory");
}

const end = performance.now();

const outputTable = result.outputs.map(output => ({
  File: path.relative(process.cwd(), output.path),
  Type: output.kind,
  Size: formatFileSize(output.size),
}));

console.table(outputTable);
const buildTime = (end - start).toFixed(2);

console.log(`\n✅ React build completed in ${buildTime}ms\n`);