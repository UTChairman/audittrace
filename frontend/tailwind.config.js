/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1a1714",
        paper: "#f3efe6",
        surface: "#fffdf8",
        elevated: "#ffffff",
        line: "#d9d0c3",
        forest: "#1f3d2b",
        moss: "#3d5a45",
        high: "#8f2d2d",
        medium: "#9a6700",
        low: "#4d6a56",
        weak: "#9a6700",
      },
      fontFamily: {
        display: ['"Source Serif 4"', "Georgia", "serif"],
        sans: ['"IBM Plex Sans"', "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(26,23,20,0.04), 0 12px 32px -18px rgba(31,61,43,0.35)",
        float: "0 18px 40px -24px rgba(26,23,20,0.45)",
      },
    },
  },
  plugins: [],
};
