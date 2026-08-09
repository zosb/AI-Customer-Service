export interface PasswordValidationResult {
  valid: boolean
  message: string
}

export function normalizeAccountInput(value: string): string {
  return value.trim()
}

export function validateAccountInput(account: string): string {
  const value = normalizeAccountInput(account)

  if (!value) {
    return '请输入邮箱或手机号'
  }

  if (value.length < 3) {
    return '账号格式不正确'
  }

  return ''
}

export function validatePassword(password: string): PasswordValidationResult {
  if (password.length < 8) {
    return { valid: false, message: '密码至少需要 8 个字符' }
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: '密码必须包含小写字母' }
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: '密码必须包含大写字母' }
  }
  if (!/\d/.test(password)) {
    return { valid: false, message: '密码必须包含数字' }
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    return { valid: false, message: '密码必须包含特殊字符' }
  }

  return { valid: true, message: '' }
}
