/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
      colors: {
        brand: { 50: "#eef4fb", 100: "#d6e4f5", 500: "#2f6db5", 600: "#245a98", 700: "#1e3a5f" },
      },
    },
  },
  plugins: [],
};
