/**
 * A small JSON Schema toolkit for the OpenAPI conformance test: example payloads generated from
 * the API's component schemas (to feed the web's zod schemas), and a validator for the request
 * bodies the web builds. It covers the subset FastAPI emits: $ref, anyOf, enum, const, objects
 * with required and additionalProperties, arrays, strings (uuid, date, date-time, length),
 * integers, numbers and booleans.
 */
export type JsonSchema = {
  $ref?: string;
  anyOf?: JsonSchema[];
  enum?: unknown[];
  const?: unknown;
  type?: string;
  format?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: boolean | JsonSchema;
  items?: JsonSchema;
  minItems?: number;
  maxItems?: number;
  minLength?: number;
  maxLength?: number;
  default?: unknown;
};

export type Components = Record<string, JsonSchema>;

export function resolve(schema: JsonSchema, components: Components): JsonSchema {
  if (!schema.$ref) return schema;
  const name = schema.$ref.split("/").pop() ?? "";
  const target = components[name];
  if (!target) throw new Error(`unknown $ref ${schema.$ref}`);
  return resolve(target, components);
}

export interface SampleOptions {
  /** `full`: every property, non-null; `minimal`: required properties only, null where allowed. */
  mode: "full" | "minimal";
  /** Which enum value to pick (modulo the enum's length), so variants cover every value. */
  pick: number;
}

const UUID = "0a8b5c2e-7d41-4a8e-9a0b-0c1d2e3f4a5b";

function stringSample(schema: JsonSchema, name: string): string {
  if (schema.format === "uuid") return UUID;
  if (schema.format === "date") return "1923-03-15";
  if (schema.format === "date-time") return "2026-10-01T12:00:00Z";
  if (name === "code") return "no_relation";
  return "texto";
}

export function sample(schema: JsonSchema, components: Components, options: SampleOptions, name = ""): unknown {
  const node = resolve(schema, components);
  if (node.const !== undefined) return node.const;
  if (node.enum) return node.enum[options.pick % node.enum.length];
  if (node.anyOf) {
    const nonNull = node.anyOf.filter((option) => resolve(option, components).type !== "null");
    const nullable = nonNull.length < node.anyOf.length;
    if (options.mode === "minimal" && nullable) return null;
    return sample(nonNull[0] ?? { type: "null" }, components, options, name);
  }
  switch (node.type) {
    case "object": {
      const out: Record<string, unknown> = {};
      for (const [key, child] of Object.entries(node.properties ?? {})) {
        if (options.mode === "minimal" && !(node.required ?? []).includes(key)) continue;
        out[key] = sample(child, components, options, key);
      }
      if (!node.properties && typeof node.additionalProperties === "object" && options.mode === "full") {
        out.paterno = sample(node.additionalProperties, components, options, "paterno");
      }
      return out;
    }
    case "array":
      return options.mode === "full" || (node.minItems ?? 0) > 0 ? [sample(node.items ?? {}, components, options, name)] : [];
    case "string":
      return stringSample(node, name);
    case "integer":
    case "number":
      return 1;
    case "boolean":
      return true;
    case "null":
      return null;
    default:
      return {};
  }
}

/** The longest enum reachable from a schema, so `pick` 0..n-1 visits every value of each. */
export function longestEnum(schema: JsonSchema, components: Components, seen = new Set<string>()): number {
  if (schema.$ref) {
    if (seen.has(schema.$ref)) return 0;
    seen.add(schema.$ref);
  }
  const node = resolve(schema, components);
  const children = [
    ...(node.anyOf ?? []),
    ...Object.values(node.properties ?? {}),
    ...(node.items ? [node.items] : []),
    ...(typeof node.additionalProperties === "object" ? [node.additionalProperties] : []),
  ];
  return Math.max(node.enum?.length ?? 0, ...children.map((child) => longestEnum(child, components, seen)), 0);
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Validates a value; returns the problems found, each with its path. */
export function validate(value: unknown, schema: JsonSchema, components: Components, path = "$"): string[] {
  const node = resolve(schema, components);
  if (node.anyOf) {
    const fits = node.anyOf.some((option) => validate(value, option, components, path).length === 0);
    return fits ? [] : [`${path}: matches no anyOf branch`];
  }
  if (node.enum && !node.enum.includes(value)) return [`${path}: ${JSON.stringify(value)} not in enum`];
  if (node.const !== undefined && node.const !== value) return [`${path}: not the constant`];
  switch (node.type) {
    case "null":
      return value === null ? [] : [`${path}: not null`];
    case "boolean":
      return typeof value === "boolean" ? [] : [`${path}: not a boolean`];
    case "integer":
      return Number.isInteger(value) ? [] : [`${path}: not an integer`];
    case "number":
      return typeof value === "number" ? [] : [`${path}: not a number`];
    case "string": {
      if (typeof value !== "string") return [`${path}: not a string`];
      const problems: string[] = [];
      if (node.format === "uuid" && !UUID_PATTERN.test(value)) problems.push(`${path}: not a uuid`);
      if (node.minLength !== undefined && value.length < node.minLength) problems.push(`${path}: too short`);
      if (node.maxLength !== undefined && value.length > node.maxLength) problems.push(`${path}: too long`);
      return problems;
    }
    case "array": {
      if (!Array.isArray(value)) return [`${path}: not an array`];
      const problems = value.flatMap((item, index) => validate(item, node.items ?? {}, components, `${path}[${index}]`));
      if (node.minItems !== undefined && value.length < node.minItems) problems.push(`${path}: too few items`);
      if (node.maxItems !== undefined && value.length > node.maxItems) problems.push(`${path}: too many items`);
      return problems;
    }
    case "object": {
      if (typeof value !== "object" || value === null || Array.isArray(value)) return [`${path}: not an object`];
      const record = value as Record<string, unknown>;
      const problems: string[] = [];
      for (const key of node.required ?? []) if (!(key in record)) problems.push(`${path}.${key}: required`);
      for (const [key, child] of Object.entries(record)) {
        const property = node.properties?.[key];
        if (property) problems.push(...validate(child, property, components, `${path}.${key}`));
        else if (node.additionalProperties === false) problems.push(`${path}.${key}: not allowed`);
        else if (typeof node.additionalProperties === "object") {
          problems.push(...validate(child, node.additionalProperties, components, `${path}.${key}`));
        }
      }
      return problems;
    }
    default:
      return [];
  }
}
