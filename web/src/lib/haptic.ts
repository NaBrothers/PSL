export function haptic(style: "light" | "medium" | "heavy" = "light") {
  if ("vibrate" in navigator) {
    const duration = style === "light" ? 10 : style === "medium" ? 25 : 50
    navigator.vibrate(duration)
  }
}

export function hapticSuccess() {
  if ("vibrate" in navigator) {
    navigator.vibrate([10, 30, 10])
  }
}
