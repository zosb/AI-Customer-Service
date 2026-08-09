import { describe, expect, it } from 'vitest'

import {
  normalizeAccountInput,
  validateAccountInput,
  validatePassword,
} from '@/utils/authValidation'

describe('auth validation', () => {
  it('trims account input', () => {
    expect(normalizeAccountInput('  user@example.com ')).toBe(
      'user@example.com',
    )
  })

  it('requires an account', () => {
    expect(validateAccountInput('   ')).toBe('请输入邮箱或手机号')
  })

  it('accepts a non-empty account for backend validation', () => {
    expect(validateAccountInput('user@example.com')).toBe('')
    expect(validateAccountInput('13800138000')).toBe('')
  })

  it.each([
    ['Aa1!', '密码至少需要 8 个字符'],
    ['PASSWORD1!', '密码必须包含小写字母'],
    ['password1!', '密码必须包含大写字母'],
    ['Password!', '密码必须包含数字'],
    ['Password1', '密码必须包含特殊字符'],
  ])('rejects weak password %s', (password, message) => {
    expect(validatePassword(password)).toEqual({
      valid: false,
      message,
    })
  })

  it('accepts a strong password', () => {
    expect(validatePassword('StrongPass1!')).toEqual({
      valid: true,
      message: '',
    })
  })
})
