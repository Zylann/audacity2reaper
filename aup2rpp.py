import struct


AU_SAMPLE_FORMAT_16 = 3
AU_SAMPLE_FORMAT_24 = 4
AU_SAMPLE_FORMAT_FLOAT = 6


def load_au_file(au_fpath):
	with open(au_fpath, 'rb') as f:

		# wxUint32 magic;      // magic number
		# wxUint32 dataOffset; // byte offset to start of audio data
		# wxUint32 dataSize;   // data length, in bytes (optional)
		# wxUint32 encoding;   // data encoding enumeration
		# wxUint32 sampleRate; // samples per second
		# wxUint32 channels; // number of interleaved channels

		hcount = 6
		hdata = struct.unpack('I' * hcount, f.read(hcount * 4))

		result = {
			'magic': hdata[0],
			'data_offset': hdata[1],
			'data_size': hdata[2],
			'encoding': hdata[3],
			'sample_rate': hdata[4],
			'channels': hdata[5]
		}

		print(result)

		if result['magic'] == 0x2e736e64:
			encoding = result['encoding']
		else:
			print("ERROR: Endianess needs to be swapped but I dunno what to do")
			return

		f.seek(result['data_offset'])

		ds = result['data_size']

		#if ds == 0xffffffff:
			# Size was specified as optional... read to end of file I guess?
			#ds = -1

		if encoding == AU_SAMPLE_FORMAT_16:
			sfc = 'h'
		elif encoding == AU_SAMPLE_FORMAT_24:
			print("ERROR: 24-bit samples? Dunno how to read them")
			return
		elif encoding == AU_SAMPLE_FORMAT_FLOAT:
			sfc = 'f'
		else:
			print("ERROR: I dunno this format ", encoding)
			return

		sample_data = []

		i = 0
		while i < ds:
			d = f.read(4)
			if len(d) == 0:
				break
			sample_data.append(struct.unpack(sfc, d)[0])
			i += 1

		ds = i

	result['data_size'] = ds
	result['encoding'] = encoding
	result['sample_data'] = sample_data

	return result


def write_wav_file(fpath, sample_rate, channels, bits_per_sample, sample_data):

	data_chunk_size = len(sample_data) * bits_per_sample // 8
	fmt_chunk_size = 2 + 2 + 4 + 4 + 2 + 2
	riff_chunk_size = 4 + (8 + fmt_chunk_size) + (8 + data_chunk_size)

	with open(fpath, 'wb') as f:

		f.write(b'RIFF')
		f.write(struct.pack('I', riff_chunk_size))

		f.write(b'WAVE')
		#wave_chunk_size = ???
		#f.write(struct.pack('I', wave_chunk_size))

		# ----------
		f.write(b'fmt ')
		f.write(struct.pack('I', fmt_chunk_size))

		# Format
		# PCM = 1 (i.e. Linear quantization) Values other than 1 indicate some form of compression.
		f.write(struct.pack('H', 1))

		f.write(struct.pack('H', channels))

		f.write(struct.pack('I', sample_rate))

		# SampleRate * NumChannels * BitsPerSample/8
		byte_rate = sample_rate * channels * bits_per_sample // 8
		f.write(struct.pack('I', byte_rate))

		# NumChannels * BitsPerSample/8
		block_align = channels * bits_per_sample // 8
		f.write(struct.pack('H', block_align))

		# 8 bits = 8, 16 bits = 16, etc.
		f.write(struct.pack('H', bits_per_sample))

		# ----------
		f.write(b'data')
		f.write(struct.pack('I', data_chunk_size))
		sfc = 'h'
		if bits_per_sample == 32:
			sfc = 'i'
		for v in sample_data:
			f.write(struct.pack(sfc, v))


def write_rpp_file(project):
	# TODO
	pass


def main():

	print("Loading AU file")
	au = load_au_file("project_data/e08/d08/e0808cd2.au")

	samples = au['sample_data']

	if au['encoding'] == AU_SAMPLE_FORMAT_FLOAT:
		print("Converting data")
		for i, v in enumerate(samples):
			# We want 16-bit PCM
			samples[i] = int(v * 32767.0)

	print("Saving WAV file")
	write_wav_file("output.wav", au['sample_rate'], au['channels'], 16, samples)

	print("Done")


main()


