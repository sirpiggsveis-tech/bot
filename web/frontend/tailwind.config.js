/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: {
          bg: "#0f1419",
          surface: "#171f29",
          border: "#26313f",
          accent: "#3fb950",
          muted: "#8b98a9",
        },
      },
    },
  },
  plugins: [],
};
