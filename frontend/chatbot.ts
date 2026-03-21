/**
 * chatbot.ts — iMessage echo bot (no Nessie, no external APIs)
 *
 * Install:  bun add @photon-ai/imessage-kit
 * Run:      bun run chatbot.ts
 *
 * Before running:
 *   System Settings → Privacy & Security → Full Disk Access → add your terminal
 */

import { IMessageSDK } from '@photon-ai/imessage-kit'

const sdk = new IMessageSDK({
  watcher: {
    pollInterval: 2000,
    excludeOwnMessages: true,
  }
})

// ── Business logic — no external calls, pure string responses ──────────────────
function processMessage(sender: string, text: string): string {
  const msg = text.toLowerCase().trim()

  if (msg === 'help') {
    return (
      '💳 FinanceBot Commands\n\n' +
      '• BALANCE — check your balance\n' +
      '• SPENDING — this month\'s summary\n' +
      '• TRANSACTIONS — recent activity\n' +
      '• HELP — show this menu'
    )
  }

  if (msg === 'balance') {
    return '💵 Your current balance is $1,240.50 (demo)'
  }

  if (msg === 'spending') {
    return '📊 This month: $842.10 across 23 transactions (demo)'
  }

  if (msg === 'transactions') {
    return (
      '📋 Recent transactions (demo):\n' +
      '• $12.50 — Starbucks\n' +
      '• $52.40 — Target\n' +
      '• $8.99 — Netflix\n' +
      '• $34.20 — Whole Foods\n' +
      '• $24.75 — Uber'
    )
  }

  // Default: echo back whatever they sent
  return `Echo: ${text}\n\nText HELP to see available commands.`
}

// ── Start watching for messages ────────────────────────────────────────────────
console.log('✅ iMessage chatbot starting...')
console.log('   Text this Mac to chat.')
console.log('   Press Ctrl+C to stop.\n')

await sdk.startWatching({
  onDirectMessage: async (msg) => {
    if (msg.isFromMe) return
    if (!msg.text)    return

    console.log(`📱 [${new Date().toLocaleTimeString()}] From ${msg.sender}: ${msg.text}`)

    try {
      const reply = processMessage(msg.sender, msg.text)
      await sdk.send(msg.sender, reply)
      console.log(`📤 Replied: ${reply}\n`)
    } catch (err) {
      console.error('❌ Error:', err)
    }
  },

  onError: (error) => {
    console.error('❌ Watcher error:', error)
  }
})
console.log('✅ Watcher started successfully')


// Graceful shutdown on Ctrl+C
process.on('SIGINT', async () => {
  console.log('\n👋 Shutting down...')
  sdk.stopWatching()
  await sdk.close()
  process.exit(0)
})