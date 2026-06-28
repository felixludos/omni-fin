import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type Asset = {
  symbol: string
  long_name?: string | null
  category?: string | null
}

type Account = {
  id: string
  name?: string | null
  type?: string | null
  institution?: string | null
}

function App() {
  const [health, setHealth] = useState<string>('checking')
  const [assets, setAssets] = useState<Asset[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])

  useEffect(() => {
    Promise.all([
      fetch('/api/health').then((r) => r.json()),
      fetch('/api/assets').then((r) => r.json()),
      fetch('/api/accounts').then((r) => r.json())
    ])
      .then(([healthData, assetData, accountData]) => {
        setHealth(healthData.status)
        setAssets(assetData)
        setAccounts(accountData)
      })
      .catch((err) => setHealth(`error: ${err}`))
  }, [])

  return (
    <main>
      <header>
        <h1>Omnifin</h1>
        <p>Backend status: <strong>{health}</strong></p>
      </header>

      <section className="grid">
        <article>
          <h2>Assets</h2>
          {assets.length === 0 ? <p>No assets loaded yet.</p> : (
            <table>
              <thead><tr><th>Symbol</th><th>Name</th><th>Category</th></tr></thead>
              <tbody>{assets.map((asset) => (
                <tr key={asset.symbol}><td>{asset.symbol}</td><td>{asset.long_name ?? ''}</td><td>{asset.category ?? ''}</td></tr>
              ))}</tbody>
            </table>
          )}
        </article>

        <article>
          <h2>Accounts</h2>
          {accounts.length === 0 ? <p>No accounts loaded yet.</p> : (
            <table>
              <thead><tr><th>Name</th><th>Type</th><th>Institution</th></tr></thead>
              <tbody>{accounts.map((account) => (
                <tr key={account.id}><td>{account.name ?? ''}</td><td>{account.type ?? ''}</td><td>{account.institution ?? ''}</td></tr>
              ))}</tbody>
            </table>
          )}
        </article>
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
