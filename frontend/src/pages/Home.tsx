import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getToken } from '../api'

export function Home() {
  const navigate = useNavigate()

  useEffect(() => {
    navigate(getToken() ? '/profile' : '/login', { replace: true })
  }, [navigate])

  return null
}
