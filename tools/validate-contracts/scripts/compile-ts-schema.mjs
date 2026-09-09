import { compile } from "json-schema-to-typescript";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const schemaPath = process.argv[2];
const title = process.argv[3];
const outputPath = process.argv[4];
const schema = JSON.parse(await readFile(schemaPath, "utf8"));
schema.title = title;
const ts = await compile(schema, title, {
  bannerComment: "",
  cwd: path.dirname(schemaPath),
  additionalProperties: false,
  unreachableDefinitions: true,
});
await writeFile(outputPath, ts);
