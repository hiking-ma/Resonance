import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  confirmLivePlan,
  fetchLivePortfolio,
  initializeLivePortfolio,
  skipLivePlan,
} from '../api/client'

const QUERY_KEY = ['livePortfolio']

export function useLivePortfolio() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchLivePortfolio,
  })
}

function useRefreshMutation<T>(mutationFn: (value: T) => Promise<unknown>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => client.invalidateQueries({ queryKey: QUERY_KEY }),
  })
}

export function useInitializeLivePortfolio() {
  return useRefreshMutation(initializeLivePortfolio)
}

export function useConfirmLivePlan() {
  return useRefreshMutation(confirmLivePlan)
}

export function useSkipLivePlan() {
  return useRefreshMutation(skipLivePlan)
}
