import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0B0E11",
          panel: "#1E222A",
          elevated: "#252932",
        },
        line: "#2A2E39",
        text: {
          DEFAULT: "#D1D4DC",
          muted: "#787B86",
          bright: "#F7F7F7",
        },
        up: "#26A69A",
        down: "#EF5350",
        accent: "#2962FF",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
