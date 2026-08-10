import {copyFile, mkdir} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const mobileDirectory = path.resolve(scriptDirectory, "..");
const repositoryDirectory = path.resolve(mobileDirectory, "..");
const dataDirectory = path.join(mobileDirectory, "web", "data");
const tierMapDirectory = path.join(dataDirectory, "tier_maps");

const libraries = [
  "dayz_crafting_library.json",
  "dayz_illness_library.json",
  "dayz_file_guide_library.json",
  "dayz_tier_guide.json"
];
const tierMaps = ["chernarus.webp", "livonia.webp", "sakhal.webp"];

await mkdir(tierMapDirectory, {recursive: true});
for (const name of libraries) {
  await copyFile(path.join(repositoryDirectory, name), path.join(dataDirectory, name));
}
for (const name of tierMaps) {
  await copyFile(path.join(repositoryDirectory, "tier_maps", name), path.join(tierMapDirectory, name));
}

console.log(`Synced ${libraries.length} DayZ libraries and ${tierMaps.length} tier maps for offline use.`);
