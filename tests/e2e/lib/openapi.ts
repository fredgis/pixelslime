/**
 * Runtime validation of real API responses against contracts/openapi.yaml.
 *
 * This is the single highest-value check in the harness: it compiles the response
 * schema for every operation in the contract and validates what W7 actually emits
 * against it, so any drift from what W6 was generated to expect surfaces as a hard
 * failure rather than a silent shape mismatch.
 *
 * Two wrinkles the contract forces on us, both reported in the W10 findings:
 *   1. The file declares `openapi: 3.1.0` (JSON Schema 2020-12) but uses the 3.0-only
 *      `nullable: true` keyword, which is not valid in 3.1. Ajv 2020 would ignore it
 *      and then reject a legitimate `null`, so we normalise `nullable: true` into the
 *      2020-12 form (`type: [..., "null"]`) before compiling.
 *   2. `$ref`s point at `#/components/schemas/*`; we embed the (normalised) components
 *      beside each response schema so those pointers resolve locally.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import yamlImport from 'js-yaml';
import Ajv2020Import from 'ajv/dist/2020.js';
import addFormatsImport from 'ajv-formats';
import type { ErrorObject, ValidateFunction } from 'ajv';

// ESM/CJS interop: these packages ship CJS, so unwrap a possible default.
const yaml = ((yamlImport as unknown as { default?: typeof yamlImport }).default ??
  yamlImport) as typeof yamlImport;
const Ajv2020 = (Ajv2020Import as unknown as { default?: unknown }).default ?? Ajv2020Import;
const addFormats = (addFormatsImport as unknown as { default?: unknown }).default ??
  addFormatsImport;

const here = dirname(fileURLToPath(import.meta.url));
const CONTRACT_PATH = resolve(here, '..', '..', '..', 'contracts', 'openapi.yaml');

type Json = Record<string, unknown>;

/** Deep-clone a plain JSON value (schemas here are plain objects/arrays/scalars). */
function clone<T>(value: T): T {
  return structuredClone(value);
}

/**
 * Rewrite OpenAPI-3.0 `nullable: true` into JSON-Schema-2020-12 nullability, in place.
 * Everything else is left untouched so validation stays faithful to the contract.
 */
function normaliseNullable(node: unknown): void {
  if (Array.isArray(node)) {
    for (const item of node) normaliseNullable(item);
    return;
  }
  if (node === null || typeof node !== 'object') return;
  const obj = node as Json;
  if (obj.nullable === true) {
    const t = obj.type;
    if (typeof t === 'string') {
      obj.type = [t, 'null'];
    } else if (Array.isArray(t)) {
      if (!t.includes('null')) t.push('null');
    } else {
      // No concrete type (e.g. a bare $ref): widen with an explicit anyOf.
      const inner = clone(obj);
      delete (inner as Json).nullable;
      for (const key of Object.keys(obj)) delete obj[key];
      obj.anyOf = [inner, { type: 'null' }];
    }
    delete obj.nullable;
  }
  for (const key of Object.keys(obj)) normaliseNullable(obj[key]);
}

export interface Contract {
  doc: Json;
  /** Compile a validator for a response schema node (components embedded for $ref). */
  compile(schemaNode: Json): ValidateFunction;
  /** The JSON response schema for an operation, or `undefined` if none is defined. */
  responseSchema(path: string, method: string, status: string): Json | undefined;
}

let cached: Contract | null = null;

export function loadContract(): Contract {
  if (cached) return cached;

  const doc = yaml.load(readFileSync(CONTRACT_PATH, 'utf8')) as Json;
  normaliseNullable(doc);
  const components = clone(doc.components ?? {}) as Json;

  const ajv = new (Ajv2020 as new (opts: unknown) => {
    compile: (s: unknown) => ValidateFunction;
  })({
    strict: false,
    allErrors: true,
    allowUnionTypes: true,
    validateFormats: true,
  });
  (addFormats as (a: unknown) => void)(ajv);

  const compile = (schemaNode: Json): ValidateFunction => {
    const schema = { ...clone(schemaNode), components: clone(components) };
    return ajv.compile(schema);
  };

  const responseSchema = (path: string, method: string, status: string): Json | undefined => {
    const paths = doc.paths as Json | undefined;
    const item = paths?.[path] as Json | undefined;
    const op = item?.[method.toLowerCase()] as Json | undefined;
    const responses = op?.responses as Json | undefined;
    const response = responses?.[status] as Json | undefined;
    const content = response?.content as Json | undefined;
    const json = content?.['application/json'] as Json | undefined;
    return (json?.schema as Json | undefined) ?? undefined;
  };

  cached = { doc, compile, responseSchema };
  return cached;
}

export interface ValidationResult {
  ok: boolean;
  errors: string[];
}

/** Validate a JSON body against the response schema for one operation. */
export function validateJson(
  path: string,
  method: string,
  status: string,
  body: unknown,
): ValidationResult {
  const contract = loadContract();
  const schema = contract.responseSchema(path, method, status);
  if (schema === undefined) {
    return { ok: false, errors: [`no application/json schema defined for ${method} ${path} ${status}`] };
  }
  const validate = contract.compile(schema);
  const ok = validate(body) as boolean;
  const errors = (validate.errors ?? []).map(
    (e: ErrorObject) => `${e.instancePath || '/'} ${e.message ?? ''}`.trim(),
  );
  return { ok, errors };
}
