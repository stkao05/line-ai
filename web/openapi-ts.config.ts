import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "openapi.json",
  output: "openapi",
  plugins: [
    "zod",
    {
      name: "@hey-api/sdk",
      validator: true,
    },
  ],
});
