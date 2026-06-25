/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        pitch: '#2d5a27',
        dark: '#1a1a2e',
        'dark-card': '#16213e',
        'dark-border': '#0f3460',
        accent: '#4fc3f7',
        danger: '#ef5350',
      },
    },
  },
  plugins: [],
}
