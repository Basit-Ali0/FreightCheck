/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        severity: {
          critical: "#dc2626",
          warning: "#d97706",
          info: "#0284c7",
        },
        confidence: {
          low: "#dc2626",
          medium: "#d97706",
          high: "#15803d",
        },
      },
    },
  },
  plugins: [],
};
