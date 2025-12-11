import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: 'http://127.0.0.1:8000/openapi.json',
  output: 'src/client',
  plugins: [
    '@hey-api/typescript',
    '@hey-api/client-axios',
    '@hey-api/sdk',
    {
      name: '@tanstack/react-query',
      queryOptions: true,
    },
  ],
});
