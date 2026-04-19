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
          passed: "#15803d",
        },
        confidence: {
          very_low: "#7f1d1d",
          low: "#dc2626",
          medium: "#d97706",
          high: "#15803d",
        },
        status: {
          processing: "#2563eb",
          complete: "#15803d",
          failed: "#dc2626",
          awaiting_review: "#d97706",
        },
      },
    },
  },
  plugins: [],
};
