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
        background: "var(--background)",
        foreground: "var(--foreground)",
        discord: {
          darkest: "#1e1f22",
          darker: "#2b2d31",
          dark: "#313338",
          card: "#2b2d31",
          border: "#383a40",
          blurple: "#5865F2",
          green: "#23a55a",
          red: "#f23f43",
          yellow: "#f0b232",
          muted: "#949ba4",
          text: "#f2f3f5",
          subtext: "#dbdee1",
        },
      },
    },
  },
  plugins: [],
};
export default config;
