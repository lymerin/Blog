import { copyFile, mkdir } from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'

const source = process.argv[2]
if (!source) throw new Error('Usage: node scripts/prepare-avatar.mjs <source-image>')

const projectRoot = process.cwd()
const assetDirectory = path.join(projectRoot, 'src', 'assets')
const publicDirectory = path.join(projectRoot, 'public')

await mkdir(assetDirectory, { recursive: true })
await copyFile(source, path.join(assetDirectory, 'avatar.png'))

await Promise.all([
  sharp(source).resize(64, 64, { fit: 'cover' }).png({ compressionLevel: 9 }).toFile(path.join(publicDirectory, 'avatar-icon.png')),
  sharp(source)
    .resize(180, 180, { fit: 'cover' })
    .png({ compressionLevel: 9 })
    .toFile(path.join(publicDirectory, 'apple-touch-icon.png')),
])
