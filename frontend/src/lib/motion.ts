import type { Transition } from 'motion/react'

export type NavigationIntent = 'replace' | 'push' | 'pop'

export const spatialSpring: Transition = {
  type: 'spring',
  bounce: 0,
  duration: 0.42,
}

export const disclosureSpring: Transition = {
  type: 'spring',
  bounce: 0,
  duration: 0.26,
}

export const fadeInTransition: Transition = {
  type: 'tween',
  duration: 0.18,
  ease: [0.16, 1, 0.3, 1],
}

export const fadeOutTransition: Transition = {
  type: 'tween',
  duration: 0.12,
  ease: [0.4, 0, 1, 1],
}

export const reducedFadeTransition: Transition = {
  type: 'tween',
  duration: 0.12,
  ease: 'easeOut',
}

export const pageOffset = 36
export const departingPageOffset = 24
export const contentOffset = 10
export const resultStagger = 0.03

