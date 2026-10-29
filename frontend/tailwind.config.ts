import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef3ff",
          100: "#dbe5ff",
          200: "#bccfff",
          300: "#8eaeff",
          400: "#5b83ff",
          500: "#3a5cff",
          600: "#2840f0",
          700: "#2131d1",
          800: "#212ca8",
          900: "#212c84",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        signature: ["'Segoe Script'", "'Brush Script MT'", "'Snell Roundhand'", "cursive"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.08)",
        lift: "0 10px 30px -12px rgba(33,49,209,.35)",
      },
    },
  },
  plugins: [],
} satisfies Config;
