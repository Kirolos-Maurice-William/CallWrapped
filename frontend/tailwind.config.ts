import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#070a0f",
          900: "#0b0e14",
          850: "#101522",
          800: "#161c2c",
          700: "#1c2436",
          600: "#263249",
          500: "#384766",
        },
      },
    },
  },
  plugins: [],
};
export default config;
