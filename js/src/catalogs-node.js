/**
 * Node-only conveniences for loading catalogs off a disk.
 *
 * The catalog format and every rule about it live in `./catalogs.js`, which
 * imports nothing and stays browser-safe. This module is the thin wrapper that
 * knows about files: it reads them with `node:fs` and hands the parsed records
 * straight to `Catalogs`. It is deliberately NOT exported from `index.js` --
 * a browser game bundling the simulator must not pull in `node:fs` -- and is
 * reached through its own subpath instead:
 *
 *     import { fromDir } from 'ems-data-simulator/catalogs-node';
 *     const catalogs = fromDir('./ke-catalog');
 *
 * JSON ONLY. Python's loader also reads CSV; parsing CSV here would mean a new
 * runtime dependency, so a `.csv` catalog is reported as unsupported rather
 * than ignored -- silently skipping it would simulate the wrong country.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { basename, extname, join } from "node:path";

import { CATALOG_KINDS, Catalogs, MANIFEST_FILENAME } from "./catalogs.js";

/** Catalog file formats this port reads. */
export const CATALOG_SUFFIXES = Object.freeze([".json"]);

/** Formats Python reads that this port does not. */
export const UNSUPPORTED_SUFFIXES = Object.freeze([".csv"]);

function stemOf(name) {
  return basename(name, extname(name));
}

function parseJSONFile(path, what) {
  let text;
  try {
    text = readFileSync(path, "utf-8");
  } catch (error) {
    throw new Error(`${path}: cannot read ${what}: ${error.message}`);
  }
  // Strip a byte-order mark, so a file Excel or Notepad saved does not turn
  // its first key into '﻿facility_name'.
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${path}: not valid JSON: ${error.message}`);
  }
}

function readRecords(path, kind) {
  const suffix = extname(path).toLowerCase();
  if (UNSUPPORTED_SUFFIXES.includes(suffix)) {
    throw new Error(
      `${path}: ${suffix} catalogs are not supported by the JavaScript port; ` +
        `convert it to ${kind}.json (the Python implementation reads both)`,
    );
  }
  if (!CATALOG_SUFFIXES.includes(suffix)) {
    throw new Error(
      `${path}: unsupported catalog format ${extname(path) || "''"}; ` +
        `expected ${CATALOG_SUFFIXES.join(" or ")}`,
    );
  }
  const payload = parseJSONFile(path, `${kind} catalog`);
  if (!Array.isArray(payload)) {
    throw new Error(
      `${path}: expected a JSON array of ${kind} records, got ` +
        `${payload === null ? "null" : typeof payload}`,
    );
  }
  return payload;
}

function isFile(path) {
  try {
    return statSync(path).isFile();
  } catch {
    return false;
  }
}

function isDirectory(path) {
  try {
    return statSync(path).isDirectory();
  } catch {
    return false;
  }
}

/**
 * Load `facilities`, `appliances` and `loggers` from a directory, each as a
 * `.json` file. A catalog with no file in the directory is left `null` -- the
 * JS port has no packaged default to fall back to.
 *
 * Names are matched case-insensitively, so the `Facilities.JSON` that several
 * exporters produce is found here. Two files that both claim the same catalog
 * is an error rather than a resolution by luck.
 *
 * A `manifest.json` in the directory is read as the catalogs' provenance and
 * exposed as `.manifest`. It is optional and its absence is silent.
 *
 * @param {string} path - Directory holding the catalog files.
 * @returns {Catalogs}
 */
export function fromDir(path) {
  if (!isDirectory(path)) {
    throw new Error(`${path}: not a catalog directory`);
  }
  const entries = readdirSync(path)
    .filter((name) => isFile(join(path, name)))
    .sort();

  const options = { sources: {} };
  const found = {};
  for (const kind of CATALOG_KINDS) {
    const matches = entries.filter(
      (name) =>
        stemOf(name).toLowerCase() === kind &&
        [...CATALOG_SUFFIXES, ...UNSUPPORTED_SUFFIXES].includes(
          extname(name).toLowerCase(),
        ),
    );
    if (matches.length > 1) {
      throw new Error(
        `${path}: found more than one ${kind} catalog file ` +
          `(${matches.join(", ")}); keep only one`,
      );
    }
    if (matches.length === 1) {
      const file = join(path, matches[0]);
      options[kind] = readRecords(file, kind);
      options.sources[kind] = file;
      found[kind] = file;
    }
  }
  if (Object.keys(found).length === 0) {
    throw new Error(
      `${path}: no catalog files found; expected any of ` +
        CATALOG_KINDS.map((kind) => `${kind}.json`).join(", "),
    );
  }

  const manifests = entries.filter(
    (name) => name.toLowerCase() === MANIFEST_FILENAME,
  );
  if (manifests.length > 1) {
    throw new Error(
      `${path}: found more than one manifest (${manifests.join(", ")}); ` +
        `keep only one`,
    );
  }
  if (manifests.length === 1) {
    const manifestPath = join(path, manifests[0]);
    const manifest = parseJSONFile(manifestPath, "manifest");
    if (manifest === null || typeof manifest !== "object" || Array.isArray(manifest)) {
      throw new Error(
        `${manifestPath}: expected a JSON object keyed by catalog kind, got ` +
          `${manifest === null ? "null" : Array.isArray(manifest) ? "array" : typeof manifest}`,
      );
    }
    for (const kind of Object.keys(manifest)) {
      if (CATALOG_KINDS.includes(kind) && !(kind in found)) {
        throw new Error(
          `${manifestPath}: describes '${kind}', but the directory has no ` +
            `${kind} catalog file; add the file or drop the entry`,
        );
      }
    }
    options.manifest = manifest;
  }
  return new Catalogs(options);
}

/**
 * Load catalogs from individual files. Anything not given is left `null`.
 *
 * @param {object} paths
 * @param {string} [paths.facilities]
 * @param {string} [paths.appliances]
 * @param {string} [paths.loggers]
 * @returns {Catalogs}
 */
export function fromFiles({ facilities, appliances, loggers } = {}) {
  const given = { facilities, appliances, loggers };
  const options = { sources: {} };
  let any = false;
  for (const kind of CATALOG_KINDS) {
    const path = given[kind];
    if (path === undefined || path === null) continue;
    if (!isFile(path)) {
      throw new Error(`${path}: no such ${kind} catalog file`);
    }
    options[kind] = readRecords(path, kind);
    options.sources[kind] = path;
    any = true;
  }
  if (!any) {
    throw new Error(
      "fromFiles() needs at least one of facilities:, appliances: or loggers:",
    );
  }
  return new Catalogs(options);
}

export { Catalogs };
