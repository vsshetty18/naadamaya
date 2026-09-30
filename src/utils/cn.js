/**
 * Joins class names, skipping anything falsy.
 *
 *   cn('px-4', isActive && 'bg-brown-500', undefined, 'rounded-card')
 *   -> "px-4 bg-brown-500 rounded-card"
 *
 * Also accepts arrays and { className: condition } objects:
 *
 *   cn(['a', 'b'], { 'text-sage-600': isGood, 'text-status-bad': !isGood })
 */
export function cn(...inputs) {
  const out = []

  const add = (input) => {
    if (!input) return

    if (typeof input === 'string' || typeof input === 'number') {
      out.push(String(input))
      return
    }

    if (Array.isArray(input)) {
      input.forEach(add)
      return
    }

    if (typeof input === 'object') {
      Object.entries(input).forEach(([className, condition]) => {
        if (condition) out.push(className)
      })
    }
  }

  inputs.forEach(add)
  return out.join(' ')
}

export default cn
