import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Async, Segmented, SyntheticBadge, Table } from '../components/ui'

describe('Async', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<Async state={{ loading: true }}>{() => <p>data</p>}</Async>)
    expect(container.querySelector('.skeleton')).toBeTruthy()
  })
  it('shows an error with retry', () => {
    const retry = vi.fn()
    render(<Async state={{ error: new Error('boom'), retry }}>{() => null}</Async>)
    expect(screen.getByRole('alert')).toHaveTextContent('boom')
    fireEvent.click(screen.getByText('Retry'))
    expect(retry).toHaveBeenCalled()
  })
  it('shows the empty state', () => {
    render(<Async state={{ data: { items: [] } }} isEmpty={(d) => !d.items.length}>{() => <p>data</p>}</Async>)
    expect(screen.getByText('No data for these filters')).toBeInTheDocument()
  })
  it('renders data', () => {
    render(<Async state={{ data: { n: 3 } }}>{(d) => <p>n={d.n}</p>}</Async>)
    expect(screen.getByText('n=3')).toBeInTheDocument()
  })
})

describe('Segmented', () => {
  it('calls onChange with the option value', () => {
    const onChange = vi.fn()
    render(<Segmented label="Granularity" value="week" onChange={onChange} options={['day', 'week']} />)
    fireEvent.click(screen.getByText(/day/i))
    expect(onChange).toHaveBeenCalledWith('day')
  })
})

describe('labels and tables', () => {
  it('marks synthetic data visibly', () => {
    render(<SyntheticBadge />)
    expect(screen.getByText(/synthetic/i)).toBeInTheDocument()
  })
  it('renders table rows', () => {
    render(<Table rowKey={(r) => r.id} rows={[{ id: 1, name: 'a' }, { id: 2, name: 'b' }]}
      columns={[{ key: 'name', label: 'Name', render: (r) => r.name }]} />)
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })
})
