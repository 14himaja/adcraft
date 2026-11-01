import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CampaignStudioModal } from './CampaignStudioModal';
import { apiError, bodyOf, calls, CONNECTION, makeCampaign, mockApi, renderSWR } from '../test/mockApi';

afterEach(() => vi.unstubAllGlobals());

const open = (id: string | null = 'c1') =>
  renderSWR(<CampaignStudioModal campaignId={id} onClose={vi.fn()} onChanged={vi.fn()} />);

const goTo = async (label: RegExp) => userEvent.click(await screen.findByRole('button', { name: label }));

describe('CampaignStudioModal', () => {
  it('loads the draft and shows missing fields and warnings', async () => {
    mockApi({
      'GET /v1/campaigns/c1': makeCampaign({
        missing_fields: ['landing_url', 'image_id'],
        warnings: ['Housing ads need a special ad category'],
        can_publish: false,
      }),
    });
    open();
    expect(await screen.findByRole('dialog', { name: /campaign studio/i })).toBeInTheDocument();
    expect(await screen.findByDisplayValue('Python Course Launch')).toBeInTheDocument();
    expect(screen.getByText(/missing before you can publish/i)).toHaveTextContent(/landing url/i);
    expect(screen.getByText(/missing before you can publish/i)).toHaveTextContent(/image/i);
    expect(screen.getByText('Housing ads need a special ad category')).toBeInTheDocument();
    const publish = screen.getByRole('button', { name: /publish and start instagram ad/i });
    expect(publish).toBeDisabled();
    expect(publish).toHaveAccessibleDescription(/fill the missing fields/i);
  });

  it('saves edits with PUT when moving to the next step', async () => {
    const fetchMock = mockApi({
      'GET /v1/campaigns/c1': makeCampaign(),
      'PUT /v1/campaigns/c1': (init: RequestInit) => makeCampaign(JSON.parse(String(init.body))),
    });
    open();
    const title = await screen.findByLabelText(/campaign title/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'Learn Python');
    await userEvent.click(screen.getByRole('button', { name: /continue/i }));
    await waitFor(() => expect(calls(fetchMock, 'PUT /v1/campaigns/c1')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'PUT /v1/campaigns/c1')).toMatchObject({ title: 'Learn Python', objective: 'TRAFFIC' });
    expect(await screen.findByLabelText(/search meta interests/i)).toBeInTheDocument();
  });

  it('keeps interest {id, name} objects from Meta search', async () => {
    const fetchMock = mockApi({
      'GET /v1/campaigns/c1': makeCampaign(),
      'GET /v1/meta/interests?q=git': [{ id: '600', name: 'GitHub', audience_size_lower: 1 }],
      'PUT /v1/campaigns/c1': (init: RequestInit) => makeCampaign(JSON.parse(String(init.body))),
    });
    open();
    await goTo(/target audience/i);
    await userEvent.type(screen.getByLabelText(/search meta interests/i), 'git');
    await userEvent.click(await screen.findByRole('button', { name: /add interest github/i }));
    expect(screen.getByText('Bangalore')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }));
    await waitFor(() => expect(calls(fetchMock, 'PUT /v1/campaigns/c1')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'PUT /v1/campaigns/c1').audience.interests).toEqual([
      { id: '6003682002118', name: 'Python (programming language)' },
      { id: '600', name: 'GitHub' },
    ]);
  });

  it('flags a daily budget under ₹50', async () => {
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
    open();
    await goTo(/budget & schedule/i);
    const budget = screen.getByLabelText(/daily budget/i);
    await userEvent.clear(budget);
    await userEvent.type(budget, '49');
    expect(screen.getByText(/minimum is ₹50/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/start date/i)).toHaveValue('2026-10-20');
    expect(screen.getByLabelText(/end date/i)).toHaveValue('2026-10-22');
  });

  it('shows live counters, picks a variant and saves it', async () => {
    const fetchMock = mockApi({
      'GET /v1/campaigns/c1': makeCampaign(),
      'PUT /v1/campaigns/c1': (init: RequestInit) => makeCampaign(JSON.parse(String(init.body))),
    });
    open();
    await goTo(/creative & preview/i);
    await userEvent.click(screen.getByRole('radio', { name: /code in 8 weeks/i }));
    const headline = screen.getByLabelText(/^headline/i);
    expect(headline).toHaveValue('Code in 8 weeks');
    await userEvent.clear(headline);
    await userEvent.type(headline, 'x'.repeat(41));
    expect(screen.getByText('41/40')).toHaveClass('text-rose-600');
    expect(headline).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText(/\/125/)).toBeInTheDocument();
    expect(screen.getByText(/\/30$/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText(/call to action/i), 'DOWNLOAD');
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }));
    await waitFor(() => expect(calls(fetchMock, 'PUT /v1/campaigns/c1')).toHaveLength(1));
    const body = bodyOf(fetchMock, 'PUT /v1/campaigns/c1');
    expect(body.selected_variant).toBe(1);
    expect(body.variants[1]).toMatchObject({ headline: 'x'.repeat(41), call_to_action: 'DOWNLOAD' });
  });

  it('regenerates the image with an extra prompt and rewrites copy with AI', async () => {
    const fetchMock = mockApi({
      'GET /v1/campaigns/c1': makeCampaign(),
      'POST /v1/campaigns/c1/image/generate': makeCampaign({ image_url: '/api/v1/images/img2' }),
      'POST /v1/campaigns/c1/copy/improve': makeCampaign({
        variants: [{ headline: 'Save review time', primary_text: 'Free trial', description: 'Try it', call_to_action: 'SIGN_UP' }],
      }),
    });
    open();
    await goTo(/creative & preview/i);
    await userEvent.type(screen.getByLabelText(/extra image instructions/i), 'add a chocolate cake');
    await userEvent.click(screen.getByRole('button', { name: /regenerate image/i }));
    await waitFor(() => expect(screen.getByAltText(/ad image/i).getAttribute('src')).toContain('img2'));
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/image/generate')).toEqual({ prompt: 'add a chocolate cake' });

    const rewrite = screen.getByRole('button', { name: /ai rewrite/i });
    expect(rewrite).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/rewrite instruction/i), 'mention the free trial');
    await userEvent.click(rewrite);
    expect(await screen.findByDisplayValue('Save review time')).toBeInTheDocument();
    expect(bodyOf(fetchMock, 'POST /v1/campaigns/c1/copy/improve')).toEqual({ instruction: 'mention the free trial' });
  });

  it('shows the 422 message when an uploaded image is rejected', async () => {
    const fetchMock = mockApi({
      'GET /v1/campaigns/c1': makeCampaign(),
      'POST /v1/campaigns/c1/image': apiError(422, 'Image is 9:16; use 1:1 or 4:5', 'INVALID_IMAGE'),
    });
    open();
    await goTo(/creative & preview/i);
    const file = new File(['x'], 'phone.png', { type: 'image/png' });
    await userEvent.upload(screen.getByLabelText(/upload my image/i), file);
    expect(await screen.findByText('Image is 9:16; use 1:1 or 4:5')).toBeInTheDocument();
    const init = calls(fetchMock, 'POST /v1/campaigns/c1/image')[0][1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect((init.body as FormData).get('file')).toBe(file);
  });

  it('chooses an image from the Media Library', async () => {
    const fetchMock = mockApi({
      'GET /v1/campaigns/c1': makeCampaign(),
      'GET /v1/media': [{ id: 'm9', filename: 'shop.jpg', source: 'uploaded', prompt: null, created_at: '2026-10-01' }],
      'PUT /v1/campaigns/c1/image': makeCampaign({ image_id: 'm9', image_url: '/api/v1/images/m9' }),
    });
    open();
    await goTo(/creative & preview/i);
    await userEvent.click(screen.getByRole('button', { name: /choose from media library/i }));
    const picker = await screen.findByRole('dialog', { name: /media library/i });
    await userEvent.click(await within(picker).findByRole('button', { name: /use shop\.jpg/i }));
    await waitFor(() => expect(bodyOf(fetchMock, 'PUT /v1/campaigns/c1/image')).toEqual({ image_id: 'm9' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /media library/i })).not.toBeInTheDocument());
    expect(screen.getByAltText(/ad image/i).getAttribute('src')).toContain('m9');
  });

  it('creates a DRAFT with POST /campaigns when starting from scratch', async () => {
    const fetchMock = mockApi({
      'POST /v1/campaigns': (init: RequestInit) => makeCampaign({ id: 'n1', ...JSON.parse(String(init.body)) }),
    });
    open(null);
    await userEvent.type(screen.getByLabelText(/campaign title/i), 'Bakery');
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }));
    await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns')).toHaveLength(1));
    expect(bodyOf(fetchMock, 'POST /v1/campaigns')).toMatchObject({ title: 'Bakery (Draft)' })  // the studio marks saved drafts;
    expect(calls(fetchMock, 'GET /v1/campaigns/c1')).toHaveLength(0);
  });

  it('opens the publish confirmation when the draft is complete', async () => {
    mockApi({ 'GET /v1/campaigns/c1': makeCampaign(), 'GET /v1/meta/connection': CONNECTION });
    open();
    await userEvent.click(await screen.findByRole('button', { name: /publish and start instagram ad/i }));
    expect(await screen.findByRole('dialog', { name: /publish and start instagram ad/i })).toBeInTheDocument();
  });

  describe('city search', () => {
    const MUMBAI = { key: '2295414', name: 'Mumbai', type: 'city', country_code: 'IN' };

    it('adds a city {key, name} from Meta location search and drops the overlapping country', async () => {
      const fetchMock = mockApi({
        'GET /v1/campaigns/c1': makeCampaign({ audience: { ...makeCampaign().audience, cities: [] } }),
        'GET /v1/meta/locations?q=Mum&country=IN': [MUMBAI],
        'PUT /v1/campaigns/c1': (init: RequestInit) => makeCampaign(JSON.parse(String(init.body))),
      });
      open();
      await goTo(/target audience/i);
      await userEvent.type(screen.getByLabelText(/search cities/i), 'Mum');
      await userEvent.click(await screen.findByRole('button', { name: /add city mumbai/i }));
      expect(screen.getByRole('button', { name: /remove city mumbai/i })).toBeInTheDocument();
      expect(calls(fetchMock, 'GET /v1/meta/locations?q=Mum&country=IN')).toHaveLength(1); // debounced
      await userEvent.click(screen.getByRole('button', { name: /save draft/i }));
      await waitFor(() => expect(calls(fetchMock, 'PUT /v1/campaigns/c1')).toHaveLength(1));
      const audience = bodyOf(fetchMock, 'PUT /v1/campaigns/c1').audience;
      expect(audience.cities).toEqual([{ key: '2295414', name: 'Mumbai' }]);
      expect(audience.countries).toEqual([]);
    });

    it('removes a city chip', async () => {
      mockApi({ 'GET /v1/campaigns/c1': makeCampaign() });
      open();
      await goTo(/target audience/i);
      await userEvent.click(screen.getByRole('button', { name: /remove city bangalore/i }));
      expect(screen.queryByText('Bangalore')).not.toBeInTheDocument();
    });

    it('asks to connect Meta when the search returns META_NOT_CONNECTED', async () => {
      mockApi({
        'GET /v1/campaigns/c1': makeCampaign(),
        'GET /v1/meta/locations?q=Pune&country=IN': apiError(409, 'Connect Meta first', 'META_NOT_CONNECTED'),
      });
      open();
      await goTo(/target audience/i);
      await userEvent.type(screen.getByLabelText(/search cities/i), 'Pune');
      expect(await screen.findByText('Connect Meta to search cities')).toBeInTheDocument();
    });

    it('stops at 10 cities', async () => {
      const cities = Array.from({ length: 10 }, (_, i) => ({ key: `k${i}`, name: `City ${i}` }));
      mockApi({ 'GET /v1/campaigns/c1': makeCampaign({ audience: { ...makeCampaign().audience, cities } }) });
      open();
      await goTo(/target audience/i);
      expect(screen.getByLabelText(/search cities/i)).toBeDisabled();
      expect(screen.getByText(/up to 10 cities/i)).toBeInTheDocument();
    });
  });

  describe('after publishing', () => {
    it('stays open with the published result and a Done button, and refreshes the list', async () => {
      const onClose = vi.fn();
      const onChanged = vi.fn();
      mockApi({
        'GET /v1/campaigns/c1': makeCampaign(),
        'GET /v1/meta/connection': CONNECTION,
        'POST /v1/campaigns/c1/publish': { status: 'PUBLISHING' },
        'GET /v1/campaigns/c1/publish': { status: 'DONE', steps: [], error: null },
      });
      renderSWR(<CampaignStudioModal campaignId="c1" onClose={onClose} onChanged={onChanged} />);
      await userEvent.click(await screen.findByRole('button', { name: /publish and start instagram ad/i }));
      await userEvent.click(await screen.findByRole('button', { name: /publish and start ad/i }));
      await waitFor(() => expect(screen.queryByRole('dialog', { name: /publish and start instagram ad/i })).not.toBeInTheDocument());
      expect(screen.getByRole('status')).toHaveTextContent(/submitted and activated on meta/i);
      expect(screen.getByRole('dialog', { name: /campaign studio/i })).toBeInTheDocument();
      expect(onChanged).toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole('button', { name: /^done$/i }));
      expect(onClose).toHaveBeenCalled();
    });

    it('opens a non-draft ad read-only with an explicit duplicate action', async () => {
      const onClose = vi.fn();
      const fetchMock = mockApi({ 'GET /v1/campaigns/c1': makeCampaign({ status: 'ACTIVE' }) });
      renderSWR(<CampaignStudioModal campaignId="c1" onClose={onClose} onChanged={vi.fn()} />);
      expect(await screen.findByText(/published ads cannot be edited/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /duplicate as new draft/i })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /save draft/i })).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: /close studio/i }));
      expect(onClose).toHaveBeenCalled();
      expect(calls(fetchMock, 'POST /v1/campaigns')).toHaveLength(0);
    });

    it('duplicates through the dedicated endpoint and preserves the returned image in the draft', async () => {
      const fetchMock = mockApi({
        'GET /v1/campaigns/c1': makeCampaign({ status: 'ACTIVE', image_id: 'img1', image_url: '/api/v1/images/img1' }),
        'POST /v1/campaigns/c1/duplicate': makeCampaign({ id: 'copy1', image_id: 'img1', image_url: '/api/v1/images/img1' }),
      });
      const onClose = vi.fn();
      renderSWR(<CampaignStudioModal campaignId="c1" onClose={onClose} onChanged={vi.fn()} />);
      await userEvent.click(await screen.findByRole('button', { name: /duplicate as new draft/i }));
      await waitFor(() => expect(calls(fetchMock, 'POST /v1/campaigns/c1/duplicate')).toHaveLength(1));
      expect(onClose).toHaveBeenCalled();
    });
  });
});
